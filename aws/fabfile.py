from fabric.api import env, sudo, run, settings, cd, local
from fabric.decorators import runs_once, roles, parallel, hosts
from fabric.operations import get, put
from fabric.tasks import execute
import fabric.contrib.files
import boto3
import sys
import os
import sys
import sqlite3
import random
from binascii import hexlify
import csv
import petlib
import matplotlib.pylab as plt
import matplotlib.mlab as mlab
import time
import json
# import shutil

# ---------------------------------
BRANCH = 'new'

ec2 = boto3.resource('ec2')

# ---------------------------------------------GET-FUNCTIONS--------------------------------------
#get the filtered aws instances
@runs_once
def get_all_instances():
    #EC2 find particular instances, filtered by the once which are runnning
    instances = ec2.instances.filter(Filters=[{'Name' : 'instance-state-name', 'Values' : ['running']}])
    inst = ['ubuntu@' + i.public_dns_name for i in instances]
    print '\n'.join(inst)
    return inst

@runs_once
def get_ec2_instance(ids):
    instances = ec2.instances.filter(InstanceIds=[ids])
    for instance in instances:
        print(instance.id, instance.state["Name"], instance.public_dns_name, instance.instance_type)

@runs_once
def get_mixnodes():
    mix_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Mixnode"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    nodes =  ['ubuntu@' + i.public_dns_name for i in mix_instances]
    print "Mixnodes", nodes
    return nodes

@runs_once
def get_clients():
    client_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Client"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    nodes = ['ubuntu@' + i.public_dns_name for i in client_instances]
    print "Client", nodes
    return nodes

@runs_once
def get_providers():
    provider_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Provider"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    nodes = ['ubuntu@' + i.public_dns_name for i in provider_instances]
    print "Providers", nodes
    return nodes


mixnodes = get_mixnodes()
clients = get_clients()
providers = get_providers()

env.roledefs.update({
    'mixnodes':mixnodes,
    'clients':clients,
    'providers':providers
    })

# --------------------------------------------------KEY FILE ------------------------------------------
env.key_filename = '/Users/ania/Documents/AWS/Loopix_keys/Loopix.pem'
# ----------------------------------------LAUNCHING-FUNCTIONS------------------------------------------

#launching new instances
def ec2start(num, typ='t2.micro'):
    instances = ec2.create_instances(
        ImageId='ami-ed82e39e',
        InstanceType=typ,
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

# ----------------------------------------STOP-AND-TERMINATE-INSTANCES------------------------------------------

@runs_once
def ec2stopAll():
    mix_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Mixnode"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    client_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Client"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    provider_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Provider"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])

    instances = list(mix_instances) + list(client_instances) + list(provider_instances)
    ids = [i.id for i in instances]
    try:
        ec2.instances.filter(InstanceIds=ids).stop()
        ec2.instances.filter(InstanceIds=ids).terminate()
    except Exception, e:
        print e


#@runs_once
def ec2stopInstance(ids):
    try:
        ec2.instances.filter(InstanceIds=[ids]).stop()
        ec2.instances.filter(InstanceIds=[ids]).terminate()
    except Exception, e:
        print e


# ----------------------------------------TAG-INSTANCES------------------------------------------
#@runs_once
def ec2tagInstance(ids, tagname):
    mytags = [{"Key":"Type", "Value":tagname}]
    ec2.create_tags(Resources=[ids], Tags=mytags)
    instances = ec2.instances.filter(InstanceIds=[ids])
    for instance in instances:
        for tag in instance.tags:
            if tag["Key"] == "Type":
                tag["Value"] = tagname
        print "Instance %s taged as %s." % (instance.id, tagname)


# ----------------------------------------LIST-ALL-INSTANCES------------------------------------------
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

# ----------------------------------------TAKE-INFO-ABOUT-INSTANCES------------------------------------------
# Check instances status
@runs_once
def ec2checkStatus():
    for status in ec2.meta.client.describe_instance_status()['InstanceStatuses']:
        print(status)


# Get instance public IP address
def ec2getIP(ids):
    instances = ec2.instances.filter(InstanceIds=[ids])
    ips = [i.public_ip_address for i in instances]
    return ips


# Get instance public DNS name
def ec2getDNS(ids):
    instances = ec2.instances.filter(InstanceIds=[ids])
    dns = [i.public_dns_name for i in instances]
    return dns
#
# # Get private IP addresses of the instances
#
# def ec2getIPs():
#     local('rm -f dns_ip_mix.csv')
#     local('rm -f dns_ip_user.csv')
#     local('rm -f dns_ip_prv.csv')
#
#     mixnodes = {}
#     clients = {}
#     providers = {}
#     mix_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Mixnode"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
#     client_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Client"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
#     provider_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Provider"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
#     for i in mix_instances:
#         mixnodes[i.public_dns_name] = i.private_ip_address
#     for i in client_instances:
#         clients[i.public_dns_name] = i.private_ip_address
#     for i in provider_instances:
#         providers[i.public_dns_name] = i.private_ip_address
#
#     with open('dns_ip_mix.csv', 'ab') as outfile:
#         csvW = csv.writer(outfile, delimiter=',')
#         csvW.writerow(['DNS', 'IP'])
#         for key in mixnodes:
#             csvW.writerow([key, mixnodes[key]])
#     with open('dns_ip_user.csv', 'ab') as outfile:
#         csvW = csv.writer(outfile, delimiter=',')
#         csvW.writerow(['DNS', 'IP'])
#         for key in clients:
#             csvW.writerow([key, clients[key]])
#     with open('dns_ip_prv.csv', 'ab') as outfile:
#         csvW = csv.writer(outfile, delimiter=',')
#         csvW.writerow(['DNS', 'IP'])
#         for key in providers:
#             csvW.writerow([key, providers[key]])
#
#
#
#--------------------------------------DEPLOY-FUNCTIONS-----------------------------------------------------------
@roles("mixnodes")
@parallel
def gitpull():
    with cd('loopix'):
        run('git pull')


@roles("mixnodes")
@parallel
def start_mixnode():
    with cd("loopix/loopix"):
        run("git checkout %s" % BRANCH)
        run("git pull")
        #run("twistd -p profiler_output.dat -y run_mixnode.py")
        run("twistd -y run_mixnode.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)


@roles("mixnodes")
@parallel
def kill_mixnode():
    with cd("loopix/loopix"):
        pid = run("cat twistd.pid", warn_only=True)
        print "Kill %s with PID %s" % (env.host, pid)
        sudo("kill `cat twistd.pid`", warn_only=True)
        run("rm -f *.csv")


@roles("clients")
@parallel
def start_client():
    with cd("loopix/loopix"):
        run("git pull")
        run("twistd -y run_client.py")
        pid = run("cat twistd.pid")
        print "Run Client on %s with PID %s" % (env.host, pid)
        run("rm -f *.csv")


@roles("clients")
@parallel
def kill_client():
    with cd("loopix/loopix"):
        pid = run("cat twistd.pid", warn_only=True)
        print "Kill %s with PID %s" % (env.host, pid)
        run("kill `cat twistd.pid`", warn_only=True)


@roles("clients")
@parallel
def start_multi_client(num):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            run("git checkout %s" % BRANCH)
            run('git pull')
            run('twistd -y run_client.py')
            pid = run('cat twistd.pid')
            print "Run Client on %s with PID %s" % (env.host, pid)


@roles("clients")
@parallel
def kill_multi_client(num):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+"/loopix/loopix"):
            pid = run("cat twistd.pid", warn_only=True)
            print "Kill %s with PID %s" % (env.host, pid)
            run("kill `cat twistd.pid`", warn_only=True)
            run("rm -f *.csv")


@roles("providers")
@parallel
def start_provider():
    with cd("loopix/loopix"):
        run("git checkout %s" % BRANCH)
        run("git pull")
        #run("twistd -p profiler_output.dat -y run_provider.py")
        run("twistd -y run_provider.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)


@roles("providers")
@parallel
def kill_provider():
    with cd("loopix/loopix"):
        pid = run("cat twistd.pid", warn_only=True)
        print "Kill %s with PID %s" % (env.host, pid)
        run("kill `cat twistd.pid`", warn_only=True)
        run("rm -f *.csv")


@parallel
def startAll():
    execute(start_mixnode)
    execute(start_provider)
    execute(start_client)


@parallel
def killAll():
    execute(kill_mixnode)
    execute(kill_provider)
    execute(kill_client)


@parallel
def startMultiAll(num):
    execute(start_mixnode)
    execute(start_provider)
    execute(start_multi_client,num)


@parallel
def killMultiAll(num):
    execute(kill_mixnode)
    execute(kill_provider)
    execute(kill_multi_client,num)


# ---------------------------------------------SETUP-AND-DEPLOY---------------------------------------
# getting file from the remote directory
@roles("mixnodes", "providers", "clients")
@parallel
def loaddirAll():
    put('example.db', 'loopix/loopix/example.db')

@roles("mixnodes")
@parallel
def loaddirTmp():
    put('../loopix/smtp_server.py', 'loopix/loopix/smtp_server.py')

#------------------------------------------------------------------------------------
@roles("mixnodes", "providers")
@parallel
def loaddirServers():
    put('example.db', 'loopix/loopix/example.db')


@roles("clients")
@parallel
def loaddirClients(num):
    for i in range(int(num)):
        put('example.db', 'client%d/loopix/loopix/example.db'%i)
#------------------------------------------------------------------------------------

@roles("clients")
@parallel
def loaddirClientsTmp(num):
    for i in range(int(num)):
        put('../loopix/smtp_server.py', 'client%d/loopix/loopix/smtp_server.py'%i)

def whoami():
    run('whoami', env.hosts)


@parallel
def setupAll(num):
    execute(setupServers)
    execute(setupClients, num)


@roles("mixnodes", "providers")
@parallel
def setupServers():
    sudo('yes '' | add-apt-repository ppa:fkrull/deadsnakes-python2.7 -y')
    sudo('apt-get -y update')
    sudo('apt-get -y install python2.7')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install --upgrade petlib')
    sudo('yes | pip install twisted==16.6.0')
    sudo('yes | pip install numpy')
    sudo('yes | pip install service_identity')
    sudo('yes | pip install sphinxmix')
    sudo('apt-get -y install htop')
    #sudo('apt-get -y install tshark')
    if fabric.contrib.files.exists("loopix"):
        with cd("loopix"):
            run("git pull")
            run("git checkout %s" % BRANCH)
    else:
        run("git clone https://github.com/UCL-InfoSec/loopix.git")


@roles("clients")
@parallel
def setupClients(num):
    sudo('yes '' | add-apt-repository ppa:fkrull/deadsnakes-python2.7 -y')
    sudo('apt-get -y update')
    sudo('apt-get -y install python2.7')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install --upgrade petlib')
    sudo('yes | pip install twisted==16.6.0')
    sudo('yes | pip install numpy')
    sudo('yes | pip install service_identity')
    sudo('yes | pip install sphinxmix')
    sudo('apt-get -y install htop')
    #sudo('apt-get -y install tshark')
    for i in range(int(num)):
        dirc = 'client%s' % i
        if not fabric.contrib.files.exists(dirc):
            run("mkdir %s" % dirc)
        with cd(dirc):
            if fabric.contrib.files.exists("loopix"):
                with cd("loopix"):
                    run("git pull")
                    run("git checkout %s" % BRANCH)
            else:
                run("git clone https://github.com/UCL-InfoSec/loopix.git")


@roles("clients")
@parallel
def setupMultiClients(num):
    sudo('yes '' | add-apt-repository ppa:fkrull/deadsnakes-python2.7')
    sudo('apt-get -y update')
    sudo('apt-get -y install python2.7')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install --upgrade petlib')
    sudo('yes | pip install twisted==16.6.0')
    sudo('yes | pip install numpy')
    sudo('yes | pip install sphinxmix')
    sudo('apt-get -y install htop')
    #sudo('apt-get -y install tshark')
    for i in range(int(num)):
        dirc = 'client%s' % i
        if not fabric.contrib.files.exists(dirc):
           run("mkdir %s" % dirc)
        with cd(dirc):
            if fabric.contrib.files.exists("loopix"):
                with cd("loopix"):
                    run("git pull")
                    run("git checkout %s" % BRANCH)
            else:
                run("git clone https://github.com/UCL-InfoSec/loopix.git")


@parallel
def test_petlib():
    run('python -c "import petlib; petlib.run_tests()"')

@runs_once
def storeProvidersNames():
    import petlib.pack
    pn = []
    for f in os.listdir('.'):
        if f.endswith(".bin"):
            with open(f, "rb") as infile:
                lines = petlib.pack.decode(infile.read())
                if lines[0] == "provider":
                    pn.append(lines[1])
    with open('providersNames.bi2', 'wb') as outfile:
        outfile.write(petlib.pack.encode(pn))

def getProvidersNames():
    import petlib.pack
    filedir = 'providersNames.bi2'
    with open(filedir, "rb") as infile:
        lines = petlib.pack.decode(infile.read())
    print lines
    return lines

@runs_once
def deployAll():
    with settings(warn_only=True):
        local("rm *.bin *.bi2 example.db")
    execute(deployMixnode)
    execute(deployProvider)
    execute(storeProvidersNames)
    execute(deployClient)
    execute(readFiles)
    execute(loaddir)

@runs_once
def deployMulti(num):
    with settings(warn_only=True):
        local("rm *.bin *.prv *.bi2 example.db")
    execute(deployMixnode)
    execute(deployProvider)
    execute(storeProvidersNames)
    execute(deployMultiClient,num)
    execute(readFiles)
    execute(loaddirServers)
    execute(loaddirClients,num)

@roles("mixnodes", "clients", "providers")
@parallel
def cleanAll():
    with cd('loopix'):
        with cd('loopix'):
            run("rm *.log* *.bin example.db *.prv log.json", warn_only=True)
#
# @roles("mixnodes", "providers")
# @parallel
# def cleanServers():
#     with cd('loopix'):
#         with cd('loopix'):
#             run("rm *.log* *.bin example.db *.prv log.json", warn_only=True)
#
# @roles("clients")
# @parallel
# def cleanClients(num):
#     for i in range(int(num)):
#         with cd('client%d/loopix/loopix'%i):
#             run("rm *.log* *.bin example.db *.prv log.json", warn_only=True)
#
# @roles("mixnodes", "clients", "providers")
# @parallel
# def cleanSetup():
#     with settings(warn_only=True):
#         run("rm -rf loopix")
#         run("rm -rf client*")
#         run("rm -rf mixnode*")
#         run("rm -rf provider*")
#
#
c = 0
@roles("mixnodes")
# @parallel
def deployMixnode():
    global c
    with cd('loopix'):
        run("git pull")
        run("git checkout %s" % BRANCH)
        N = hexlify(os.urandom(8))
        with cd('loopix'):
            run("python setup_mixnode.py 9999 %s Mix%s %s" % (str(env.host), N, 0))
            get('publicMixnode.bin', 'publicMixnode-%s.bin'%env.host)
        c += 1

@roles("clients")
@parallel
def deployClient():
    with cd("loopix"):
        run("git pull")
        run("git checkout %s" % BRANCH)
        N = hexlify(os.urandom(8))
        providers = getProvidersNames()
        prvName = random.choice(providers)
        with cd('loopix'):
            run("python setup_client.py 9999 %s Client%s %s" % (str(env.host), N, prvName))
            get('publicClient.bin', 'publicClient-%s.bin'%env.host)


@roles("clients")
@parallel
def deployMultiClient(num):
    local('rm -f testMap.csv')
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc):
            with cd('loopix'):
                run("git pull")
                run("git checkout %s" % BRANCH)
            with cd('loopix/loopix'):
                N = hexlify(os.urandom(8))
                providers = getProvidersNames()
                prvName = random.choice(providers)
                port = int(9999 - i)
                print "CLIENT: Client%s" % N
                run("python setup_client.py %d %s Client%s %s" % (port, str(env.host), N, prvName))
                get('publicClient.bin', 'publicClient-%d-%s.bin'%(port, env.host))
                with open('testMap.csv', 'a') as outfile:
                    csvW = csv.writer(outfile)
                    csvW.writerow(['Client%s'%N, dirc])


@roles("providers")
@parallel
def deployProvider():
    with cd("loopix"):
        run("git pull")
        run("git checkout %s" % BRANCH)
        N = hexlify(os.urandom(8))
        with cd("loopix"):
            run("python setup_provider.py 9999 %s Provider%s" % (str(env.host), N))
            get('publicProvider.bin', 'publicProvider-%s.bin'%env.host)


def test_experiment(mixes, providers, clients):
    execute(ec2start_mixnode_instance, mixes)
    execute(ec2start_provider_instance, providers)
    execute(ec2start_client_instance, clients)

@parallel
def setup(clients):
    execute(setupServers)
    execute(setupMultiClients, clients)

def deploy(clients):
    execute(deployMulti, clients)
#
# @roles("providers")
# def checkHost():
#     print env.host
#
#
# @runs_once
# def takeNamesDb():
#     database = "example.db"
#     db = sqlite3.connect(database)
#     c = db.cursor()
#     c.execute("SELECT * FROM Providers")
#     providers = c.fetchall()
#     for p in providers:
#         print p
#
#
@runs_once
def readFiles():
    import petlib.pack

    sys.path += ["../loopix"]
    local("rm -f example.db")

    #import databaseConnect as dc
    from database_connect import DatabaseManager
    databaseName = "example.db"
    dbManager = DatabaseManager(databaseName)
    dbManager.create_users_table("Users")
    dbManager.create_providers_table("Providers")
    dbManager.create_mixnodes_table("Mixnodes")

    for f in os.listdir('.'):
        if f.endswith(".bin"):
            with open(f, 'rb') as fileName:
                lines = petlib.pack.decode(fileName.read())
                print 'Lines: ', lines
                if lines[0] == "client":
                    dbManager.insert_row_into_table('Users',
                        [None, lines[1], lines[2], lines[3],
                        sqlite3.Binary(petlib.pack.encode(lines[4])),
                        lines[5]])
                elif lines[0] == "mixnode":
                    dbManager.insert_row_into_table('Mixnodes',
                            [None, lines[1], lines[2], lines[3],
                            sqlite3.Binary(petlib.pack.encode(lines[5])), lines[4]])
                elif lines[0] == "provider":
                    dbManager.insert_row_into_table('Providers',
                        [None, lines[1], lines[2], lines[3],
                        sqlite3.Binary(petlib.pack.encode(lines[4]))])
                else:
                    assert False
    dbManager.close_connection()
#
# def checkDB_write():
#     import petlib.pack
#
#     sys.path += ["../loopix"]
#     import databaseConnect as dc
#     databaseName = "example.db"
#     db = dc.connectToDatabase(databaseName)
#     c = db.cursor()
#     c.execute("SELECT * FROM Mixnodes")
#     data = c.fetchall()
#     for i in data:
#         print i
#
#
#
# #========================================GET COMMENDS============================================
# @roles("providers")
# @parallel
# def getPerformanceProviders():
#     with settings(warn_only=True):
#         local("rm -f performanceProvider*.csv")
#     get('loopix/loopix/performanceProvider.csv', 'performanceProvider-%s.csv'%env.host)
#
#
# @roles("mixnodes")
# @parallel
# def getPerformanceMixnodes():
#     with settings(warn_only=True):
#         local("rm -f performanceMixnode*.csv")
#     get('loopix/loopix/performanceMixnode.csv', 'performanceMixnode-%s.csv'%env.host)
#
#
# @parallel
# def getPerformance():
#     execute(getPerformanceProviders)
#     execute(getPerformanceMixnodes)
#
#
# @roles("clients")
# @parallel
# def getMessagesSent(num):
#     with settings(warn_only=True):
#         local("rm -f messagesSent*.csv")
#     #for i in range(int(num)):
#     i = random.randrange(0, int(num))
#     dirc = 'client%d'%i
#     get(dirc+'/loopix/loopix/messagesSent.csv', 'messagesSent_client%d.csv'%i)
#
#
# @roles("providers")
# @parallel
# def getLatencyProvider():
#     with settings(warn_only=True):
#         local("rm -f latency_provider*.csv")
#     get('loopix/loopix/latency.csv', 'latency_provider%s.csv'%env.host)
#
# @roles("mixnodes")
# @parallel
# def getLatencyMixnode():
#     with settings(warn_only=True):
#         local("rm -f latency_mixnode*.csv")
#     get('loopix/loopix/latency.csv', 'latency_mixnode%s.csv'%env.host)
#
# @parallel
# def getLatency():
#     execute(getLatencyProvider)
#     execute(getLatencyMixnode)
#
#
# @roles("providers")
# @parallel
# def getPIDdata():
#     with settings(warn_only="True"):
#         local("rm -f PID/PIDcontrolVal*.csv")
#     get("loopix/loopix/PIDcontrolVal.csv", "PID/PIDcontrolVal-%s.csv"%env.host)
#
# def readPIDdata():
#     for f in os.listdir('./PID'):
#         print f
#         if f.startswith('PIDcontrolVal'):
#             print "File: ", f
#             try:
#                 with open('./PID/' + f, 'rb') as infile:
#                     csvR = csv.reader(infile)
#                     for row in csvR:
#                         print row
#             except Exception, e:
#                 print str(e)
#
#
# @roles("clients")
# @parallel
# def takeClientsData(num):
#     for i in range(int(num)):
#         with cd('client%d/loopix/loopix'%i):
#             get('publicClient.bin', 'publicClient-%d-%s.bin'%((9999-i),env.host))
#
# @roles("mixnodes")
# @parallel
# def takeMixnodesData():
#     with cd('loopix/loopix'):
#         get('publicMixnode.bin', 'publicMixnode-%s.bin'%env.host)
#
# @roles("providers")
# @parallel
# def takeProvidersData():
#     with cd('loopix/loopix'):
#         get('publicProvider.bin', 'publicProvider-%s.bin'%env.host)
#     execute(storeProvidersNames)
#
# @runs_once
# def takeData(num):
#     execute(takeClientsData, num)
#     execute(takeMixnodesData)
#     execute(takeProvidersData)
#     execute(readFiles)
#
# @runs_once
# @roles("mixnodes", "clients", "providers")
# def killPythonProcess():
#     run("pkill -f *.py")
#
#
# #======================================TSHARK========================================
# @roles("mixnodes", "providers")
# @parallel
# def run_tshark(time):
#     #sudo('yes | dpkg-reconfigure wireshark-common')
#     #sudo('yes | gpasswd -a $USER wireshark')
#     with settings(warn_only=True, remote_interrupt=True):
#         run('rm -f tcpOut.pcap')
#         assert(env.remote_interrupt)
#         run('touch tcpOut.pcap')
#         sudo('chmod o=rw tcpOut.pcap')
#         # sudo('tshark -n -f udp -e frame.number -e frame.time -e ip.src -e ip.dst -e udp.srcport -e udp.dstport -e udp.port -e udp.length -T fields -a duration:%s -w tcpOut.pcap' % str(time))
#         sudo('tshark -n -f udp -e frame.time -e frame.time_delta -e ip.src -e ip.dst -e udp.srcport -e udp.dstport -e udp.port -e udp.length -T fields -a duration:%s -w tcpOut.pcap' % str(time))
# #======================================================================================
#
#
# @roles("providers")
# @parallel
# def get_tcpdumpOutput_provider():
#     with settings(warn_only=True):
#         local('rm -f tcpOut_provider*')
#     get('tcpOut.pcap', 'tcpOut_provider_%s.pcap' % env.host)
#
#
# @roles("clients")
# @parallel
# def get_tcpdumpOutput_client():
#     with settings(warn_only=True):
#         local('rm -f tcpOut_client*')
#     get('tcpOut.pcap', 'tcpOut_client_%s.pcap' % env.host)
#
#
# @roles("mixnodes")
# @parallel
# def get_tcpdumpOutput_mixnode():
#     with settings(warn_only=True):
#         local('rm -f tcpOut_mixnode*')
#     get('tcpOut.pcap', 'tcpOut_mixnode_%s.pcap' % env.host)
#
# @parallel
# def get_tcpdumpOutput():
#     execute(get_tcpdumpOutput_provider)
#     execute(get_tcpdumpOutput_client)
#     execute(get_tcpdumpOutput_mixnode)
#
#
# @roles("clients", "providers")
# @parallel
# def interruptProcess():
#     with settings(warn_only=True, remote_interrupt=True):
#         sudo('kill -2 $(ps -e | pgrep tcpdump)')
#
#
# def run_multiple_clients(subpath, numClients):
#
#     for i in range(5, 101, 5):
#         execute(run_clients, i)
#         time.sleep(1805)
#         execute(getPerformance)
#         local("mkdir performance_%d_%s" % (i, subpath))
#         local("cp performanceProvider*.csv performance_%d_%s" % (i, subpath))
#         local("cp performanceMixnode*.csv performance_%d_%s" % (i, subpath))
#         execute(killMultiAll, i)
#         execute(reset_config, int(numClients))
#
#
# def update_config_file(new_rate_payload, new_rate_loops, new_rate_drop, new_mix_loop, delay):
#     configFile = '../loopix/config.json'
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(new_rate_payload)
#         _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = str(new_rate_loops)
#         _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = str(new_rate_drop)
#         _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = str(delay)
#
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = str(new_rate_drop)
#     #local('rm -f %s' % configFile)
#
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#
# @roles('mixnodes', 'providers')
# @parallel
# def upload_config_file_servers():
#     put('../loopix/config.json', 'loopix/loopix/config.json')
#
#
# @roles('clients')
# @parallel
# def upload_config_file_clients(numClients):
#     for i in range(int(numClients)):
#         put('../loopix/config.json', 'client%d/loopix/loopix/config.json'%i)
#
#
@roles("clients")
@parallel
def run_clients(num):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            run("git checkout %s" % BRANCH)
            run('twistd -y run_client.py')
            pid = run('cat twistd.pid')
            print "Run Client on %s with PID %s" % (env.host, pid)
#
# @roles("mixnodes", "providers")
# @parallel
# def reset_config_servers(branch):
#     with cd("loopix/loopix"):
#         run("git checkout %s" % branch)
#         run('git reset --hard')
#
# @roles("clients")
# @parallel
# def reset_config_clients(num, branch):
#     for i in range(int(num)):
#         dirc = 'client%s' % i
#         with cd(dirc+'/loopix/loopix'):
#             #sudo('rm -f config.json')
#             run("git checkout %s" % branch)
#             run('git reset --hard')
#
#
# @roles("mixnodes", "providers")
# @parallel
# def update_git_servers(branch):
#     with cd("loopix/loopix"):
#         run("git checkout %s" % branch)
#         run("git pull")
#
# @roles("clients")
# @parallel
# def update_git_clients(num, branch):
#     for i in range(int(num)):
#         dirc = 'client%s' % i
#         with cd(dirc+'/loopix/loopix'):
#             run("git checkout %s" % branch)
#             run('git pull')
#
# def update_git(numClients, branch):
#     execute(update_git_servers, branch)
#     execute(update_git_clients, int(numClients), branch)
#
#
#
@roles('mixnodes')
@parallel
def run_mixnode():
    with cd('loopix/loopix'):
        run("git checkout %s" % BRANCH)
        run("twistd -y run_mixnode.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)


@roles('providers')
@parallel
def run_provider():
    with cd('loopix/loopix'):
        run("git checkout %s" % BRANCH)
        run("twistd -y run_provider.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)

@parallel
def run_all(num):
    execute(run_mixnode)
    execute(run_provider)
    execute(run_clients, num)
#
#
# # ==============================================================================
#
# @parallel
# def exp_setup(client):
#     execute(setupServers)
#     execute(setupClients, int(client))
#
# @runs_once
# def exp_deploy(clients):
#     with settings(warn_only=True):
#         local("rm *.bin *.bi2 example.db")
#     execute(deployMixnode)
#     execute(deployProvider)
#     execute(storeProvidersNames)
#     execute(deployMultiClient,int(clients))
#     execute(readFiles)
#     execute(loaddirServers)
#     execute(loaddirClients,int(clients))
#
# def read_in_mapping():
#     mapping = {}
#     with open('testMap.csv', 'r') as infile:
#         csvR = csv.reader(infile)
#         for row in csvR:
#             mapping[row[0]] = row[1]
#     return mapping
#
#
# @roles("clients")
# @parallel
# def upload_to_dirc(fileName, dirc):
#     put('../loopix/config.json', '%s/loopix/loopix/config.json'%dirc)
#
#
# @roles("clients")
# @parallel
# def run_client_id(dirc, branch):
#     with cd(dirc+'/loopix/loopix'):
#         run("git checkout %s" % branch)
#         run('twistd -y run_client.py')
#         pid = run('cat twistd.pid')
#         print "Run Client on %s with PID %s" % (env.host, pid)
#
#
# @roles("clients")
# @parallel
# def run_all_clients(numClients, branch):
#     for i in range(int(numClients)):
#         dirc = 'client%d' % i
#         with cd(dirc+'/loopix/loopix'):
#             run("git checkout %s" % branch)
#             run('twistd -y run_client.py')
#             pid = run('cat twistd.pid')
#             print "Run Client on %s with PID %s" % (env.host, pid)
#
#
# # ================================================================================================
#
# @parallel
# def test_correlation(branch, numC, run_all, delay, loopParam=None, dropParam=None, payloadParam=None, loopMixParam=None):
#     configFile = '../loopix/config.json'
#     execute(git_reset_and_update, branch, int(numC))
#     # We run two senders and two recipients. We observe the traffic going out
#     # of Pa1 and Pa2 and traffic comming to the recipients providers (Pb1, Pb2)
#     # Base on the observation I want to verify how the users are communicating
#     # (Pa1 -> Pb1 and Pa2 -> Pb2) vs (Pa1 -> Pb2 and Pa2 -> Pb1)
#     # One sender is putting messages into the buffer every 2 sec, whereas second sender is putting
#     # every 5 seconds
#
#     # ---------------------------SET-PARAMS--------------------
#     execute(set_config_params,d=delay,lC=loopParam,dC=dropParam,pC=payloadParam,lM=loopMixParam)
#     execute(set_testmode, False)
#     execute(upload_config_file_servers)
#     execute(upload_config_file_clients, int(numC))
#     # ------------------------------SELECTING-TARGET-USERS-----------------------------
#     mapping = read_in_mapping()
#     # Picks two random users who from now on are the target sender and recipient
#     data = read_from_db('example.db', 'Users')
#     providersList = set()
#     for x in data:
#         providersList.add(x[5])
#     providersList = list(providersList)
#     print providersList
#     p1_clients = [x for x in data if x[5] == providersList[0]]
#     p2_clients = [x for x in data if x[5] == providersList[1]]
#     p3_clients = [x for x in data if x[5] == providersList[2]]
#     p4_clients = [x for x in data if x[5] == providersList[3]]
#
#     A1 = random.choice(p1_clients)
#     A2 = random.choice(p2_clients)
#     B1 = random.choice(p3_clients)
#     B2 = random.choice(p4_clients)
#
#     mapping = read_in_mapping()
#     dircA1 = mapping[A1[1]]
#     dircA2 = mapping[A2[1]]
#     dircB1 = mapping[B1[1]]
#     dircB2 = mapping[B2[1]]
#
#     pair1 = [(A1, dircA1), (B1, dircB1)]
#     pair2 = [(A2, dircA2), (B2, dircB2)]
#
#     # --------------------------------UPDATE_TARGET_USERS--------------------------------------
#
#     # ---------------------------------SET_ALL_TARGET_USERS------------------------------------
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["TARGETUSER"] = "True"
#         _PARAMS["parametersClients"]["FAKE_MESSAGING"] = "1"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = str(B1[1])
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(payloadParam)
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#     execute(upload_to_dirc, 'configFile.json', dircA1)
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["TARGETUSER"] = "True"
#         _PARAMS["parametersClients"]["FAKE_MESSAGING"] = "1"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = str(B2[1])
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(payloadParam)
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#     execute(upload_to_dirc, 'configFile.json', dircA2)
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["TARGETUSER"] = "False"
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "False"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = "None"
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#     execute(upload_to_dirc, 'configFile.json', dircB1)
#     execute(upload_to_dirc, 'configFile.json', dircB2)
#     # ----------------------------SET_OTHER_USERS----------------------------------------------
#     # TO DO
#     # ---------------------------RUN_AND_TAKE_MEASURMENTS--------------------------------------
#     execute(run_mixnode, 'sphinx')
#     execute(run_provider, 'sphinx')
#     if not run_all:
#         execute(run_client_id, dircA1, 'sphinx')
#         execute(run_client_id, dircA2, 'sphinx')
#         execute(run_client_id, dircB1, 'sphinx')
#         execute(run_client_id, dircB2, 'sphinx')
#     else:
#         execute(run_all_clients, int(numC), 'sphinx')
#
#     print "----------------PAIR-1-------------------------"
#     for i in pair1:
#         print (i[0][1], i[1], i[0][5])
#     print "----------------PAIR-2--------------------------"
#     for i in pair2:
#         print (i[0][1], i[1], i[0][5])
#
#     with open("pair.csv", "a") as outfile:
#         csvW = csv.writer(outfile, delimiter=',')
#         csvW.writerow(["Pair1", "Pair2"])
#         csvW.writerow([pair1, pair2])
#         csvW.writerow(["--------", "-------"])
#     print "Saved pair in a file."
#
#
#     time.sleep(1200)
#     execute(run_tshark, 900)
#     print "------TSHARK ENDED--------"
#     execute(get_tcpdumpOutput_mixnode)
#     execute(get_tcpdumpOutput_provider)
#
#     execute(killMultiAll, int(numC))
#     execute(git_reset_and_update, branch, int(numC))
#
#
#
# def set_config_params(d, lC, dC, pC, lM):
#     # Function used for setting particular params in the config file
#     configFile = '../loopix/config.json'
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = str(d)
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(pC)
#         if lC == None:
#             _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = "None"
#         else:
#             _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = str(lC)
#         if dC == None:
#             _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = "None"
#         else:
#             _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = str(dC)
#         if lM == None:
#             _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = "None"
#         else:
#             _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = str(lM)
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#         _PARAMS["parametersClients"]["TARGETUSER"] = "False"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = ""
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#
# def set_testmode(testmode=False):
#     configFile = '../loopix/config.json'
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["TESTMODE"] = str(testmode)
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#
#
# @parallel
# def exp_correlation_attack(branch, numC):
#     execute(test_correlation, branch, int(numC), False, 0.05, None, None, 2, None)
#     try:
#         os.remove("correlation_test0")
#     except OSError:
#         pass
#     local("mkdir correlation_test0")
#     local("cp tcpOut_*.pcap correlation_test0")
#
#     execute(test_correlation, branch, int(numC), False, 0.05, None, None, 2, None)
#     try:
#         os.remove("correlation_test01")
#     except OSError:
#         pass
#     local("mkdir correlation_test01")
#     local("cp tcpOut_*.pcap correlation_test01")
#
#
#     execute(test_correlation, branch, int(numC), False, 0.05, None, None, 2, None)
#     try:
#         os.remove("correlation_test02")
#     except OSError:
#         pass
#     local("mkdir correlation_test02")
#     local("cp tcpOut_*.pcap correlation_test02")
#
#
#     execute(test_correlation, branch, int(numC), True, 0.0, None, None, 2, None)
#     try:
#         os.remove("correlation_test1")
#     except OSError:
#         pass
#     local("mkdir correlation_test1")
#     local("cp tcpOut_*.pcap correlation_test1")
#
#
#     execute(test_correlation, branch, int(numC), True, 0.05, None, None, 2, None)
#     try:
#         os.remove("correlation_test2")
#     except OSError:
#         pass
#     local("mkdir correlation_test2")
#     local("cp tcpOut_*.pcap correlation_test2")
#
#     execute(test_correlation, branch, int(numC), True, 0.5, None, None, 2, None)
#     try:
#         os.remove("correlation_test3")
#     except OSError:
#         pass
#     local("mkdir correlation_test3")
#     local("cp tcpOut_*.pcap correlation_test3")
#
#
#     execute(test_correlation, branch, int(numC), True, 5, None, None, 2, None)
#     try:
#         os.remove("correlation_test4")
#     except OSError:
#         pass
#     local("mkdir correlation_test4")
#     local("cp tcpOut_*.pcap correlation_test4")
#
#
#     execute(test_correlation, branch, int(numC), True, 10, None, None, 2, None)
#     try:
#         os.remove("correlation_test5")
#     except OSError:
#         pass
#     local("mkdir correlation_test5")
#     local("cp tcpOut_*.pcap correlation_test5")
#
#
# @parallel
# def git_reset_and_update(branch, numClients):
#     execute(reset_config_clients, int(numClients), branch)
#     execute(reset_config_servers, branch)
#     execute(update_git_clients, int(numClients), branch)
#     execute(update_git_servers, branch)
#
# @roles('clients')
# @parallel
# def upload_non_target(numClients, targetDirc):
#     for i in range(int(numClients)):
#         dirc = 'client%d' % i
#         if not dirc in targetDirc:
#             put('../loopix/config.json', '%s/loopix/loopix/config.json'%dirc)
#         else:
#             print "[%s] > THIS IS A TARGET DIRECTORY, I DO NOT UPLOAD HERE" % dirc
#
#
# def read_from_db(databaseName, tableName):
#     sys.path += ["../loopix"]
#     import databaseConnect as dc
#
#     db = dc.connectToDatabase(databaseName)
#     c = db.cursor()
#     c.execute("SELECT * FROM %s" % tableName)
#     data = c.fetchall()
#     return data
#
# def see_content(databaseName, tableName):
#     data = read_from_db(databaseName, tableName)
#     print data
#
#
# def check_provider():
#     data = read_from_db('example.db', 'Users')
#     for u in data:
#         print u
#
# def take_random_users():
#     data = read_from_db('example.db', 'Users')
#     tS = random.choice(data)
#     others = [x for x in data if not x[5] == tS[5]]
#     tR = random.choice(others)
#     return (tS, tR)
#
# def take_random_client():
#     data = read_from_db('example.db', 'Users')
#     for d in data:
#         print d
#     c = random.choice(data)
#     return c
#
#
# @parallel
# def exp_measure_latency(branch, numC, delay, loopParam, dropParam, payloadParam, loopMixParam):
#     configFile = '../loopix/config.json'
#     execute(git_reset_and_update, branch, int(numC))
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = str(delay)
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(payloadParam)
#         _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = str(loopParam)
#         _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = str(dropParam)
#         _PARAMS["parametersClients"]["TARGETUSER"] = "False"
#         _PARAMS["parametersClients"]["TESTMODE"] = "True"
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = "None"
#
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = str(loopMixParam)
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"] = str(delay)
#         _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"] = "True"
#
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#     execute(upload_config_file_servers)
#     execute(upload_config_file_clients, int(numC))
#
#     execute(run_mixnode, branch)
#     execute(run_provider, branch)
#     execute(run_all_clients, int(numC), branch)
#
#     time.sleep(3600)
#     execute(run_tshark, 400)
#     execute(get_tcpdumpOutput_mixnode)
#
#     execute(getLatency)
#     execute(killMultiAll, int(numC))
#     # reset changes to avoid git commit
#     execute(git_reset_and_update, branch, int(numC))
#
#
# @parallel
# def exp_run(branch, numC, delay, loopParam, dropParam, payloadParam, loopMixParam):
#     configFile = '../loopix/config.json'
#     execute(git_reset_and_update, branch, int(numC))
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = str(delay)
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(payloadParam)
#         _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = str(loopParam)
#         _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = str(dropParam)
#         _PARAMS["parametersClients"]["TARGETUSER"] = "False"
#         _PARAMS["parametersClients"]["TESTMODE"] = "True"
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = "None"
#
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = str(loopMixParam)
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"] = str(delay)
#         _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"] = "True"
#
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#     execute(upload_config_file_servers)
#     execute(upload_config_file_clients, int(numC))
#
#     execute(run_mixnode, branch)
#     execute(run_provider, branch)
#     execute(run_all_clients, int(numC), branch)
#
#
#
# @parallel
# def exp_latency_vs_clients(branch, numC):
#     configFile = '../loopix/config.json'
#     execute(git_reset_and_update, branch, int(numC))
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = "0"
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = "2"
#         _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = "2"
#         _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = "2"
#         _PARAMS["parametersClients"]["TARGETUSER"] = "False"
#         _PARAMS["parametersClients"]["TESTMODE"] = "True"
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = "None"
#
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = "2"
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"] = "0"
#         _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"] = "True"
#
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
#     execute(upload_config_file_servers)
#     execute(upload_config_file_clients, int(numC))
#
#     for i in range(500, int(numC)+1, 50):
#         execute(run_mixnode, branch)
#         execute(run_provider, branch)
#         execute(run_all_clients, i, branch)
#
#         time.sleep(2400)
#         try:
#             with settings(warn_only=True):
#                 shutil.rmtree('latency_%d' % i)
#         except OSError:
#             print "Did not find 'latency_%d'" % i
#         local('mkdir latency_%d' % i)
#
#         # execute(run_tshark, 600)
#         # execute(get_tcpdumpOutput_mixnode)
#         execute(getLatency)
#         local("cp latency_provider*.csv latency_%d" % int(i))
#         local("cp latency_mixnode*.csv latency_%d" % int(i))
#         # local("cp tcpOut_mixnode*.pcap latency_%d" % int(i))
#
#         execute(killMultiAll, int(numC))
#     execute(git_reset_and_update, branch, int(numC))
#
#
# @parallel
# def init_config():
#     configFile = '../loopix/config.json'
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = "0.001"
#         _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = "20"
#         _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = "60"
#         _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = "60"
#         _PARAMS["parametersClients"]["TARGETUSER"] = "False"
#         _PARAMS["parametersClients"]["TESTMODE"] = "True"
#         _PARAMS["parametersClients"]["TURN_ON_SENDING"] = "True"
#         _PARAMS["parametersClients"]["TARGETRECIPIENT"] = "None"
#
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = "60"
#         _PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"] = "0.001"
#         _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"] = "True"
#
#     with open(configFile, 'w') as f:
#         json.dump(_PARAMS, f, indent=4)
#
# @parallel
# def experiment_increasing_payload(branch, numC):
#     configFile = '../loopix/config.json'
#     execute(git_reset_and_update, branch, int(numC))
#
#     #execute(init_config)
#     execute(upload_config_file_servers)
#     execute(upload_config_file_clients, int(numC))
#
#
#     with open(configFile) as infile:
#         _PARAMS = json.load(infile)
#         old_rate_payload = float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"])
#         old_rate_cover = float(_PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"])
#
#     C = 2.0
#
#     for i in range(40):
#         if i > 0:
#             new_rate_payload = float(60.0/((60.0/old_rate_payload) + C))
#             new_rate_cover = float(60.0/((60.0/old_rate_cover) + C))
#
#             #new_rate_payload, new_rate_loops, new_rate_drop, new_mix_loop, delay
#             execute(update_config_file, new_rate_payload, new_rate_cover, new_rate_cover, new_rate_cover, 0.001)
#             execute(upload_config_file_servers)
#             execute(upload_config_file_clients, int(numC))
#             old_rate_payload = new_rate_payload
#             old_rate_cover = new_rate_cover
#
#         execute(run_mixnode, branch)
#         execute(run_provider, branch)
#         execute(run_all_clients, int(numC), branch)
#         time.sleep(1205)
#         execute(run_tshark, 300)
#         execute(get_tcpdumpOutput_mixnode)
#         execute(get_tcpdumpOutput_provider)
#         execute(getPerformance)
#         execute(getLatency)
#         #
#         local('mkdir performance%d_%d' % (int(numC), i+2+17))
#         local("cp performanceProvider*.csv performance%d_%d" % (int(numC), i+2+17))
#         local("cp performanceMixnode*.csv performance%d_%d" % (int(numC), i+2+17))
#         local("cp latency_provider*.csv performance%d_%d" % (int(numC), i+2+17))
#         local("cp latency_mixnode*.csv performance%d_%d" % (int(numC), i+2+17))
#         local("cp tcpOut_*.pcap performance%d_%d" % (int(numC), i+2+17))
#
#         execute(killMultiAll, int(numC))
#         execute(git_reset_and_update, branch, int(numC))
#
