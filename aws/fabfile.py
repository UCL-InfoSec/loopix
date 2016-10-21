from fabric.api import env, sudo, run, settings, cd, local
from fabric.decorators import runs_once, roles, parallel
from fabric.operations import get, put
from fabric.tasks import execute 
import fabric.contrib.files
import boto3
import sys
import os
import petlib.pack
import sys
import sqlite3
import random
from binascii import hexlify
import csv

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

@runs_once
def get_board():
    board_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Board"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    return ['ubuntu@' + i.public_dns_name for i in board_instances]


mixnodes = get_mixnodes()
clients = get_clients()
providers = get_providers()
board = get_board()

env.roledefs.update({
    'mixnodes':mixnodes,
    'clients':clients,
    'providers':providers,
    'board':board
    })

env.key_filename = '../keys/Loopix.pem'

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
    clients = ec2start(num, typ='t2.large')
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
def ec2start222():
    execute(ec2start_mixnode_instance, 2)
    execute(ec2start_provider_instance, 2)
    execute(ec2start_client_instance, 2)

@runs_once
def experiment1(mnum, pnum, cnum):
    execute(ec2start_mixnode_instance, mnum)
    execute(ec2start_provider_instance, pnum)
    execute(ec2start_client_instance, cnum)

@runs_once
#stoping and terminating instace
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

@runs_once
def ec2stopInstance(ids):
    try:
        ec2.instances.filter(InstanceIds=[ids]).stop()
        ec2.instances.filter(InstanceIds=[ids]).terminate()
    except Exception, e:
        print e

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


#--------------------------------------DEPLOY-FUNCTIONS-----------------------------------------------------------
@parallel
def gitpull():
    with cd('loopix'):
        run('git pull')

#--------------------------------------EXPERIMENTS-FUNCTIONS------------------------------------------------------

@roles("mixnodes")
@parallel
def start_mixnode():
    with cd("loopix/loopix"):
        run("git pull")
        run("twistd -y run_mixnode.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)


@roles("mixnodes")
@parallel
def kill_mixnode():
    with cd("loopix/loopix"):
        pid = run("cat twistd.pid", warn_only=True)
        print "Kill %s with PID %s" % (env.host, pid)
        run("kill `cat twistd.pid`", warn_only=True)


@roles("clients")
@parallel
def start_client():
    with cd("loopix/loopix"):
        run("git pull")
        run("twistd -y run_client.py")
        pid = run("cat twistd.pid")
        print "Run Client on %s with PID %s" % (env.host, pid)

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
        run("git pull")
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
        
@runs_once
@parallel
def startAll():
    execute(start_mixnode)
    execute(start_provider)
    execute(start_client)

@runs_once
@parallel
def killAll():
    execute(kill_mixnode)
    execute(kill_provider)
    execute(kill_client)

@runs_once
@parallel
def startMultiAll(num):
    execute(start_mixnode)
    execute(start_provider)
    execute(start_multi_client,num)

@runs_once
@parallel
def killMultiAll(num):
    execute(kill_mixnode)
    execute(kill_provider)
    execute(kill_multi_client,num)


@roles("boards")
@parallel
def start_board():
    run("python run_board.py")


# ---------------------------------------------SETUP-AND-DEPLOY---------------------------------------
# getting file from the remote directory
@roles("mixnodes", "providers", "clients")
@parallel
def loaddirAll():
    put('example.db', 'loopix/loopix/example.db')

@roles("mixnodes", "providers")
@parallel
def loaddirServers():
    put('example.db', 'loopix/loopix/example.db')

@roles("clients")
@parallel
def loaddirClients(num):
    for i in range(int(num)):
        put('example.db', 'client%d/loopix/loopix/example.db'%i)

def whoami():
    run('whoami', env.hosts)

@roles("mixnodes", "clients", "providers","board")
@parallel
def setupAll():
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install petlib')
    sudo('yes | pip install twisted')
    sudo('yes | pip install numpy')
    if fabric.contrib.files.exists("loopix"):
        with cd("loopix"):
            run("git pull")
    else:
        run("git clone https://github.com/UCL-InfoSec/loopix.git")


@roles("mixnodes", "providers")
@parallel
def setupServers():
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install petlib')
    sudo('yes | pip install twisted')
    sudo('yes | pip install numpy')
    if fabric.contrib.files.exists("loopix"):
        with cd("loopix"):
            run("git pull")
    else:
        run("git clone https://github.com/UCL-InfoSec/loopix.git")


@roles("clients")
@parallel
def setupMultiClients(num):
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install petlib')
    sudo('yes | pip install twisted')
    sudo('yes | pip install numpy')
    for i in range(int(num)):
        dirc = 'client%s' % i
        if not fabric.contrib.files.exists(dirc):
           run("mkdir %s" % dirc)
        with cd(dirc): 
            if fabric.contrib.files.exists("loopix"):
                with cd("loopix"):
                    run("git pull")
            else:
                run("git clone https://github.com/UCL-InfoSec/loopix.git")


@parallel
def test_petlib():
    run('python -c "import petlib; petlib.run_tests()"')

@runs_once
def storeProvidersNames():
    pn = []
    for f in os.listdir('.'):
        if f.endswith(".bin"):
            with open(f, "rb") as infile:
                lines = petlib.pack.decode(infile.read())
                if lines[0] == "provider":
                    pn.append(lines[1])
    with open('providersNames.bi2', 'wb') as outfile:
        outfile.write(petlib.pack.encode(pn))

@runs_once
def getProvidersNames():
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
        local("rm *.bin *.bi2 example.db")
    execute(deployMixnode)
    execute(deployProvider)
    execute(storeProvidersNames)
    execute(deployMultiClient,num)
    execute(readFiles)
    execute(loaddirServers)
    execute(loaddirClients,num)

@roles("mixnodes", "clients", "providers","board")
@parallel
def cleanAll():
    with cd('loopix'):
        with cd('loopix'):
            run("rm *.log* *.bin example.db *.prv log.json", warn_only=True)

@roles("mixnodes")
@parallel
def deployMixnode():
    with cd('loopix'):
        run("git pull")
        N = hexlify(os.urandom(8))
        with cd('loopix'):
            run("python setup_mixnode.py 9999 %s Mix%s" % (str(env.host), N))
            get('publicMixnode.bin', 'publicMixnode-%s.bin'%env.host)

@roles("clients")
@parallel
def deployClient():
    with cd("loopix"):
        run("git pull")
        N = hexlify(os.urandom(8))
        providers = getProvidersNames()
        prvName = random.choice(providers)
        with cd('loopix'):
            run("python setup_client.py 9999 %s Client%s %s" % (str(env.host), N, prvName))
            get('publicClient.bin', 'publicClient-%s.bin'%env.host)


@roles("clients")
@parallel
def deployMultiClient(num):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc):
            with cd('loopix'):
                run("git pull")
            with cd('loopix/loopix'):
                N = hexlify(os.urandom(8))
                providers = getProvidersNames()
                print providers
                prvName = random.choice(providers)
                port = int(9999 - i)
                run("python setup_client.py %d %s Client%s %s" % (port, str(env.host), N, prvName))
                get('publicClient.bin', 'publicClient-%d-%s.bin'%(port, env.host))     


@roles("providers")
@parallel
def deployProvider():
    with cd("loopix"):
        run("git pull")
        N = hexlify(os.urandom(8))
        with cd("loopix"):
            run("python setup_provider.py 9999 %s Provider%s" % (str(env.host), N))
            get('publicProvider.bin', 'publicProvider-%s.bin'%env.host)

@roles("providers")
def checkHost():
    print env.host


@runs_once
def takeNamesDb():
    database = "example.db"
    db = sqlite3.connect(database)
    c = db.cursor()
    c.execute("SELECT * FROM Providers")
    providers = c.fetchall()
    for p in providers:
        print p


@runs_once
def readFiles():
    sys.path += ["../loopix"]
    local("rm -f example.db")

    import databaseConnect as dc
    databaseName = "example.db"
    db = dc.connectToDatabase(databaseName)
    c = db.cursor()
    dc.createUsersTable(db, "Users")
    dc.createProvidersTable(db, "Providers")
    dc.createMixnodesTable(db, "Mixnodes")

    for f in os.listdir('.'):
        if f.endswith(".bin"):
            with open(f, 'rb') as fileName:
                lines = petlib.pack.decode(fileName.read())
                print lines
                if lines[0] == "client":
                    insertQuery = "INSERT INTO Users VALUES(?, ?, ?, ?, ?, ?)"
                    c.execute(insertQuery, [None, lines[1], lines[2], lines[3], 
                        sqlite3.Binary(petlib.pack.encode(lines[4])),
                        lines[5]])
                elif lines[0] == "mixnode":
                    insertQuery = "INSERT INTO Mixnodes VALUES(?, ?, ?, ?, ?)"
                    c.execute(insertQuery, [None, lines[1], lines[2], lines[3],
                        sqlite3.Binary(petlib.pack.encode(lines[4]))])
                elif lines[0] == "provider":
                    insertQuery = "INSERT INTO Providers VALUES(?, ?, ?, ?, ?)"
                    c.execute(insertQuery, [None, lines[1], lines[2], lines[3],
                        sqlite3.Binary(petlib.pack.encode(lines[4]))])
                else:
                    assert False
    db.commit()

@roles("mixnodes")
@parallel
def getPerformance():
    with settings(warn_only=True):
        local("rm -f *.csv")
    get('loopix/loopix/performance.csv', 'performance-%s.csv'%env.host)

def readPerformance():
    for f in os.listdir('.'):
        if f.startswith("performance"):
            print "File : %s" % f
            try:
                with open(f, 'rb') as infile:
                    csvR = csv.reader(infile)
                    for row in csvR:
                        print row
            except Exception, e:
                print str(e)

@roles("clients")
@parallel
def getMessagesSent(num):
    with settings(warn_only=True):
        local("rm -f *.csv")
    for i in range(int(num)):
        dirc = 'client%d'%i
        get(dirc+'/loopix/loopix/messagesSent.csv', 'messagesSent_client%d.csv'%i)

@roles("providers")
@parallel
def getMessagesReceived():
    with settings(warn_only=True):
        local("rm -f *.csv")
    get('loopix/loopix/messagesReceived.csv', 'messagesReceived-%s.csv'%env.host)

def readMessagesSent():
    for f in os.listdir('.'):
        if f.startswith('messagesSent'):
            print "File: ", f
            try:
                with open(f, 'rb') as infile:
                    csvR = csv.reader(infile)
                    for row in csvR:
                        print row
            except Exception, e:
                print str(e)

def readMessagesReceived():
    for f in os.listdir('.'):
        if f.startswith('messagesReceived'):
            print "File: ", f
            try:
                with open(f, 'rb') as infile:
                    csvR = csv.reader(infile)
                    for row in csvR:
                        print row
            except Exception, e:
                print str(e)

@roles("clients")
@parallel
def takeClientsData(num):
    for i in range(int(num)):
        with cd('client%d/loopix/loopix'%i):
            get('publicClient.bin', 'publicClient-%d-%s.bin'%((9999-i),env.host))

@roles("mixnodes")
@parallel
def takeMixnodesData():
    with cd('loopix/loopix'):
        get('publicMixnode.bin', 'publicMixnode-%s.bin'%env.host)

@roles("providers")
@parallel
def takeProvidersData():
    with cd('loopix/loopix'):
        get('publicProvider.bin', 'publicProvider-%s.bin'%env.host)
    execute(storeProvidersNames)

@runs_once
def takeData(num):
    execute(takeClientsData, num)
    execute(takeMixnodesData)
    execute(takeProvidersData)
    execute(readFiles)
        
