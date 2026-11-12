"""One-time, scoped AWS setup for GDPeso. Run with the approved AWS admin session."""

import argparse
import json

import boto3
from botocore.exceptions import ClientError


ACCOUNT = '173677044880'
REGION = 'us-east-1'
BUCKET = 'msi-gdpeso-releases-173677044880-us-east-1'
INSTANCE = 'i-068efaae507c5294d'
HOST_ROLE = 'ust-capstone-courtiq-delivery'
GITHUB_ROLE = 'gdpeso-github-production'
DOCUMENT = 'GDPeso-DeployProduction'
OIDC = 'token.actions.githubusercontent.com'
SUBJECT = 'repo:FrancisIGP@75497349/BI-Capstone@1448663628:ref:refs/heads/main'
OBJECTS = f'arn:aws:s3:::{BUCKET}/gdpeso/releases/*'


def policy(*statements):
    return {'Version': '2012-10-17', 'Statement': list(statements)}


TRUST = policy({
    'Effect': 'Allow', 'Principal': {'Federated': f'arn:aws:iam::{ACCOUNT}:oidc-provider/{OIDC}'},
    'Action': 'sts:AssumeRoleWithWebIdentity',
    'Condition': {'StringEquals': {f'{OIDC}:aud': 'sts.amazonaws.com', f'{OIDC}:sub': SUBJECT}},
})
DEPLOY = policy(
    {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': OBJECTS},
    {'Effect': 'Allow', 'Action': 'ssm:SendCommand', 'Resource': [
        f'arn:aws:ec2:{REGION}:{ACCOUNT}:instance/{INSTANCE}',
        f'arn:aws:ssm:{REGION}:{ACCOUNT}:document/{DOCUMENT}',
    ]},
    {'Effect': 'Allow', 'Action': 'ssm:GetCommandInvocation', 'Resource': '*',
     'Condition': {'StringEquals': {'aws:RequestedRegion': REGION}}},
)
HOST_READ = policy({'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': OBJECTS})


def absent(operation, allowed_errors):
    try:
        operation()
    except ClientError as error:
        if error.response['Error']['Code'] in allowed_errors:
            return True
        raise
    return False


def command_document():
    patterns = {
        'ArtifactKey': r'^gdpeso/releases/[a-f0-9]{40}/[1-9][0-9]{0,19}-[1-9][0-9]{0,3}\.tar\.gz$',
        'Sha256': r'^[a-f0-9]{64}$', 'Revision': r'^[a-f0-9]{40}$',
        'RunId': r'^[1-9][0-9]{0,19}$', 'RunAttempt': r'^[1-9][0-9]{0,3}$',
    }
    return {
        'schemaVersion': '2.2', 'description': 'Activate a verified GDPeso static artifact on its approved instance',
        'parameters': {key: {'type': 'String', 'allowedPattern': pattern, 'interpolationType': 'ENV_VAR'}
                       for key, pattern in patterns.items()},
        'mainSteps': [{'action': 'aws:runShellScript', 'name': 'deployGDPeso', 'inputs': {
            'timeoutSeconds': '180', 'runCommand': [
                '/usr/bin/python3 -I /usr/local/lib/gdpeso/deploy.py --artifact-key "$SSM_ArtifactKey" '
                '--sha256 "$SSM_Sha256" --revision "$SSM_Revision" --run-id "$SSM_RunId" --run-attempt "$SSM_RunAttempt"',
            ],
        }}],
    }


def main(apply):
    aws = boto3.Session(region_name=REGION)
    assert aws.client('sts').get_caller_identity()['Account'] == ACCOUNT, 'Unexpected AWS account'
    iam, ec2, s3, ssm = (aws.client(service) for service in ('iam', 'ec2', 's3', 'ssm'))
    instance = ec2.describe_instances(InstanceIds=[INSTANCE])['Reservations'][0]['Instances'][0]
    profile = instance['IamInstanceProfile']['Arn'].rsplit('/', 1)[-1]
    roles = iam.get_instance_profile(InstanceProfileName=profile)['InstanceProfile']['Roles']
    assert [role['RoleName'] for role in roles] == [HOST_ROLE], 'Shared EC2 role changed'
    managed = ssm.describe_instance_information(Filters=[{'Key': 'InstanceIds', 'Values': [INSTANCE]}])
    assert managed['InstanceInformationList'][0]['PingStatus'] == 'Online', 'SSM agent is offline'
    iam.get_open_id_connect_provider(OpenIDConnectProviderArn=f'arn:aws:iam::{ACCOUNT}:oidc-provider/{OIDC}')
    assert absent(lambda: s3.head_bucket(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT), {'404', 'NoSuchBucket'}), 'Bucket already exists'
    assert absent(lambda: iam.get_role(RoleName=GITHUB_ROLE), {'NoSuchEntity'}), 'Deployment role already exists'
    assert absent(lambda: ssm.describe_document(Name=DOCUMENT), {'InvalidDocument'}), 'Deployment document already exists'
    assert absent(lambda: iam.get_role_policy(RoleName=HOST_ROLE, PolicyName='gdpeso-read-releases'), {'NoSuchEntity'}), 'Host policy already exists'
    if not apply:
        print('GDPESO_AWS_PREFLIGHT_OK')
        return

    s3.create_bucket(Bucket=BUCKET)
    s3.put_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, PublicAccessBlockConfiguration={
        'BlockPublicAcls': True, 'IgnorePublicAcls': True, 'BlockPublicPolicy': True, 'RestrictPublicBuckets': True,
    })
    s3.put_bucket_encryption(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, ServerSideEncryptionConfiguration={
        'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}],
    })
    s3.put_bucket_lifecycle_configuration(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, LifecycleConfiguration={
        'Rules': [{'ID': 'ExpireGDPesoArtifacts', 'Status': 'Enabled', 'Filter': {'Prefix': 'gdpeso/releases/'},
                   'Expiration': {'Days': 30}}],
    })
    s3.put_bucket_policy(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, Policy=json.dumps(policy({
        'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
        'Resource': [f'arn:aws:s3:::{BUCKET}', f'arn:aws:s3:::{BUCKET}/*'],
        'Condition': {'Bool': {'aws:SecureTransport': 'false'}},
    }, {
        'Effect': 'Deny', 'Principal': {'AWS': f'arn:aws:iam::{ACCOUNT}:root'}, 'Action': 's3:PutObject',
        'Resource': OBJECTS, 'Condition': {'Null': {'s3:if-none-match': 'true'}},
    })))
    ssm.create_document(Name=DOCUMENT, Content=json.dumps(command_document()), DocumentType='Command', DocumentFormat='JSON')
    iam.create_role(RoleName=GITHUB_ROLE, AssumeRolePolicyDocument=json.dumps(TRUST), MaxSessionDuration=3600)
    iam.put_role_policy(RoleName=GITHUB_ROLE, PolicyName='gdpeso-deploy', PolicyDocument=json.dumps(DEPLOY))
    iam.put_role_policy(RoleName=HOST_ROLE, PolicyName='gdpeso-read-releases', PolicyDocument=json.dumps(HOST_READ))
    print('GDPESO_AWS_READY')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
