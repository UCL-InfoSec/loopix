from fabric.api import env, sudo, run, settings, cd
from fabric.decorators import runs_once, roles, parallel
from fabric.tasks import execute 
import boto3
import sys
import os

mytags = [{"Key":"Type", "Value":"Mixnode"}]

ec2 = boto3.resource('ec2')

# ---------------------------------------------GET-FUNCTIONS--------------------------------------
#get the filtered aws instances
def get_all_instances():
	#EC2 find particular instances, filtered by the once which are runnning
	instances = ec2.instances.filter(Filters=[{'Name' : 'instance-state-name', 'Values' : ['running']}])
	return ['ubuntu@' + i.public_dns_name for i in instances]

@runs_once
def get_ec2_instance(ids):
	instances = ec2.instances.filter(InstanceIds=[ids])
	for instance in instances:
		print(instance.id, instance.state["Name"], instance.public_dns_name, instance.instance_type)

@runs_once
def get_mixnodes():
	mix_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Mixnode"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
	return ['ubuntu@' + i.public_dns_name for i in mix_instances]

@runs_once
def get_clients():
	client_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Client"]}])
	return ['ubuntu@' + i.public_dns_name for i in client_instances]

@runs_once
def get_providers():
	provider_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Provider"]}])
	return ['ubuntu@' + i.public_dns_name for i in provider_instances]

@runs_once
def get_board():
	board_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Board"]}])
	return ['ubuntu@' + i.public_dns_name for i in board_instances]


mixnodes = get_mixnodes()
print "Hello : ", mixnodes
clients = get_clients()
providers = get_providers()
board = get_board()

env.roledefs.update({
	'mixnodes':mixnodes,
	'clients':clients,
	'providers':providers,
	'board':board
	})
env.key_filename = '/Users/ania/Documents/LoopixKeys/Loopix.pem'

# ----------------------------------------LAUNCHING-FUNCTIONS------------------------------------------

@runs_once
#launching new instances
def ec2start(num):
    instances = ec2.create_instances( 
        ImageId='ami-ed82e39e', 
        InstanceType='t2.micro',
        SecurityGroupIds= [ 'sg-42444b26' ],
        KeyName="Loopix",
        MinCount=int(num), 
        MaxCount=int(num)
        )
    return instances

@runs_once
def ec2start_mixnode_instance(num):
	mixnodes = ec2start(num)
	for i in mixnodes:
		ec2tagInstance(i.id, "Mixnode")

@runs_once
def ec2start_client_instance(num):
	clients = ec2start(num)
	for i in clients:
		ec2tagInstance(i.id, "Client")

@runs_once
def ec2start_provider_instance(num):
	providers = ec2start(num)
	for i in providers:
		ec2tagInstance(i.id, "Provider")

@runs_once
def ec2start_board_instance(num=1):
	boards = ec2start(num)
	for i in boards:
		ec2tagInstance(i.id, "Board")

@runs_once
def ec2start_taged_instance(num, tag):
	instances = ec2start(num)
	for i in instances:
		ec2tagInstance(i.id, tag) 

@runs_once
#stoping and terminating instace
def ec2stopAll():
	instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
	ids = [i.id for i in instances]
	try:
		ec2.instances.filter(InstanceIds=ids).stop()
		ec2.instances.filter(InstanceIds=ids).terminate()
	except Exception, e:
		print e

@runs_once
def ec2stopInstance(ids):
  	try:
  		ec2.instances.filter(InstanceIds=[ids]).stop()
  		ec2.instances.filter(InstanceIds=[ids]).terminate()
  	except Exception, e:
  		print e

@runs_once
def ec2tagInstance(ids, tagname):
	ec2.create_tags(Resources=[ids], Tags=mytags)
	instances = ec2.instances.filter(InstanceIds=[ids])
	for instance in instances:
		for tag in instance.tags:
			if tag["Key"] == "Type":
				tag["Value"] = tagname
		print "Instance %s taged as %s." % (instance.id, tagname)

#list all instances
@runs_once
def ec2listAll():
	instances = ec2.instances.all()
	for instance in instances:
		print(instance.id, instance.state["Name"], instance.public_dns_name, instance.instance_type)

#list all running instances
@runs_once
def ec2listAllRunning():
	instances = ec2.instances.filter(Filters=[{'Name':'instance-state-name', 'Values':['running']}])
	print("Running EC2 instances: ")
	for instance in instances:
		print(instance.id, instance.instance_type, instance.public_dns_name)

#check instances status
@runs_once
def ec2checkStatus():
	for status in ec2.meta.client.describe_instance_status()['InstanceStatuses']:
		print(status)

def ec2getIP(ids):
	instances = ec2.instances.filter(InstanceIds=[ids])
	ips = [i.public_ip_addess for i in instances]
	return ips

def ec2getDNS(ids):
	instances = ec2.instances.filter(InstanceIds=[ids])
	dns = [i.public_dns_name for i in instances]
	return dns


#--------------------------------------DEPLOY-FUNCTIONS-----------------------------------------------------
@parallel
def gitpull():
	with cd('home/ubuntu/projects/loopix'):
		# run, which is similar to local but runs remotely instead of locally.
		run('git pull')

def deploy():
	execute(gitpull)


#--------------------------------------EXPERIMENTS-FUNCTIONS------------------------------------------------------

@roles("mixnodes")
@parallel
def start_mixnode():
	run("python run_mixnode.py")
	#instance.public_dns_name how to add this?

@roles("clients")
@parallel
def start_client():
	run("python run_client.py")

@roles("providers")
@parallel
def start_provider():
	run("python run_provider.py")

@roles("boards")
@parallel
def start_board():
	run("python run_board.py")


# putting file from the remote directory
def uploaddir():
	#put - Upload one or more files to a remote host. put(argv, kwargs) - put files from argv to kwargs
	#put will honor cd, so relative values in remote_path will be prepended by the current remote working directory, if applicable.
	with cd('path'):
		put('directory_local', 'directory_remote')

def uploaddata():
	with cd('path'):
		put('directory_local', 'directory_remote')

# getting file from the remote directory
def loaddir():
	with cd('path'):
		get('directory_local', 'directory_remote')

def whoami():
    run('whoami', env.hosts)

@roles("mixnodes", "clients", "providers","board")
@parallel
def setup():
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install petlib')
    sudo('yes | pip install twisted')
    sudo('yes | pip install sqlite3')

@parallel
def test_petlib():
    run('python -c "import petlib; petlib.run_tests()"')

@roles("mixnodes")#, "clients", "providers","board")
#@parallel
def deploy():
	code_dir = '/home/ubuntu/projects/loopix'
	with settings(warn_only=True):
		sudo('rm -rf /home/ubuntu/projects/loopix')
		sudo('mkdir /home/ubuntu/projects/loopix')
	with cd('/home/ubuntu/projects'):
		sudo('pip install petlib --upgrade')
		run("git clone https://aniampio@bitbucket.org/aniampio/repo.git")






