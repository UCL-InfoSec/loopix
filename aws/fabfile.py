from fabric.api import env, sudo, run, settings, cd, local
from fabric.decorators import runs_once, roles, parallel
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
from scipy.stats import norm
import matplotlib.mlab as mlab
import time
import subprocess
from scapy.all import *

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
def ec2start(num, typ='m4.2xlarge'):
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
    clients = ec2start(num, typ='m4.4xlarge')
    for i in clients:
        ec2tagInstance(i.id, "Client")

@runs_once
def ec2start_provider_instance(num):
    providers = ec2start(num, typ='m4.2xlarge')
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
def start_mixnode(test):
    with cd("loopix/loopix"):
        if test=="True":
            run("git checkout develop")
        run("git pull")
        run("twistd -p profiler_output.dat -y run_mixnode.py")
        #run("twistd -y run_mixnode.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)


@roles("mixnodes")
@parallel
def kill_mixnode():
    with cd("loopix/loopix"):
        pid = run("cat twistd.pid", warn_only=True)
        print "Kill %s with PID %s" % (env.host, pid)
        run("kill `cat twistd.pid`", warn_only=True)
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
def start_multi_client(num, test):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            if test=="True":
                run("git checkout develop")
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
def start_provider(test):
    with cd("loopix/loopix"):
        if test=="True":
            run("git checkout develop")
        run("git pull")
        run("twistd -p profiler_output.dat -y run_provider.py")
        #run("twistd -y run_provider.py")
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

@parallel
def startMultiAll(num, test="False"):
    print "Started"
    execute(start_mixnode, test)
    execute(start_provider, test)
    execute(start_multi_client,num, test)

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

@parallel
def setupAll(num):
    execute(setupServers)
    execute(setupClients, num)   

# @roles("mixnodes", "clients", "providers","board")
# @parallel
# def setupAll():
#     sudo('apt-get -y update')
#     sudo('apt-get -y dist-upgrade')
#     sudo('apt-get -y install python-pip python-dev build-essential')
#     sudo('apt-get -y install libssl-dev libffi-dev git-all')
#     sudo('yes | pip install --upgrade pip')
#     sudo('yes | pip install --upgrade virtualenv')
#     sudo('yes | pip install petlib')
#     sudo('yes | pip install twisted')
#     sudo('yes | pip install numpy')
#     if fabric.contrib.files.exists("loopix"):
#         with cd("loopix"):
#             run("git pull")
#     else:
#         run("git clone https://github.com/UCL-InfoSec/loopix.git")


@roles("mixnodes", "providers")
@parallel
def setupServers():
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install --upgrade petlib')
    sudo('yes | pip install twisted')
    sudo('yes | pip install numpy')
    sudo('yes | pip install service_identity')
    sudo('apt-get install htop')
    if fabric.contrib.files.exists("loopix"):
        with cd("loopix"):
            run("git pull")
    else:
        run("git clone https://github.com/UCL-InfoSec/loopix.git")


@roles("clients")
@parallel
def setupClients(num):
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install --upgrade petlib')
    sudo('yes | pip install twisted')
    sudo('yes | pip install numpy')
    sudo('yes | pip install service_identity')
    sudo('apt-get install htop')
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


@roles("clients")
@parallel
def setupMultiClients(num):
    sudo('apt-get -y update')
    sudo('apt-get -y dist-upgrade')
    sudo('apt-get -y install python-pip python-dev build-essential')
    sudo('apt-get -y install libssl-dev libffi-dev git-all')
    sudo('yes | pip install --upgrade pip')
    sudo('yes | pip install --upgrade virtualenv')
    sudo('yes | pip install --upgrade petlib')
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

@runs_once
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

@roles("mixnodes", "providers")
@parallel
def cleanServers():
    with cd('loopix'):
        with cd('loopix'):
            run("rm *.log* *.bin example.db *.prv log.json", warn_only=True)

@roles("clients")
@parallel
def cleanClients(num):
    for i in range(int(num)):
        with cd('client%d/loopix/loopix'%i):
            run("rm *.log* *.bin example.db *.prv log.json", warn_only=True)

@roles("mixnodes", "clients", "providers")
@parallel
def cleanSetup():
    with settings(warn_only=True):
        run("rm -rf loopix")
        run("rm -rf client*")
        run("rm -rf mixnode*")
        run("rm -rf provider*")

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
    import petlib.pack

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

@roles("providers")
@parallel
def getPerformanceProviders():
    with settings(warn_only=True):
        local("rm -f performanceProvider*.csv")
    get('loopix/loopix/performanceProvider.csv', 'performanceProvider-%s.csv'%env.host)

@roles("mixnodes")
@parallel
def getPerformanceMixnodes():
    with settings(warn_only=True):
        local("rm -f performanceMixnode*.csv")
    get('loopix/loopix/performanceMixnode.csv', 'performanceMixnode-%s.csv'%env.host)

@runs_once
def getPerformance():
    execute(getPerformanceProviders)
    execute(getPerformanceMixnodes)

@roles("mixnodes")
@parallel
def getTimeitMixnode():
    with settings(warn_only=True):
        local("rm -f timeitMixnode*.csv")
    get('loopix/loopix/timeit.csv', 'timeitMixnode-%s.csv'%env.host)

@roles("providers")
@parallel
def getTimeitProvider():
    with settings(warn_only=True):
        local("rm -f timeitProvider*.csv")
    get('loopix/loopix/timeit.csv', 'timeitProvider-%s.csv'%env.host)

def getTimeit():
    execute(getTimeitMixnode)
    execute(getTimeitProvider)

def readTimeit():
    data = []
    for f in os.listdir('.'):
        if f.startswith("timeit"):
            print "File : %s" % f
            with open(f, 'rb') as infile:
                csvR = csv.reader(infile)
                for row in csvR:
                    data.append(float(row[0]))
                plt.plot(data, 'b', marker='x')
                plt.show()    
            data = []

def readPerformance():
    import numpy 
    #self.measurments.append([self.bProcessed, self.gbReceived, self.bReceived, self.hbSent, self.hbRec, self.pProcessed])
    bBefProc = []
    mReceived = []
    bGoodProc = []
    payProc = []
    bProcMix = []
    bGoodMix = []
    mRecvMix = []
    hbSent = []
    hbRec = []
    for f in os.listdir('.'):
        if f.startswith("performanceProvider"):
            print "File : %s" % f
            try:
                with open(f, 'rb') as infile:
                    csvR = csv.reader(infile)
                    for row in csvR:
                        bBefProc.append(float(row[0]))
                        bGoodProc.append(float(row[1]))
                        mReceived.append(float(row[2]))
                        payProc.append(float(row[3]))
                print "NUMBER OF messages processed by datagramReceive function"
                print bBefProc
                print "NUMBER OF ROUT messages processed by datagramReceive function"
                print bGoodProc
                print "NUMBER OF MESSAGES received (counted at datagramReceive)"
                print mReceived

                plt.figure(1)
                plt.subplot(211)
                plt.plot(bBefProc, 'b', marker='x')
                plt.plot(bGoodProc, 'r', marker='x', alpha=0.7)
                plt.plot(payProc, 'g', marker='x')
                plt.plot(mReceived, 'y', marker='x', alpha=0.3)
                plt.grid(True)
                plt.xlabel('t')
                plt.ylabel('Number of messages processed')

                plt.subplot(212)
                plt.plot(mReceived, marker='x')
                plt.grid(True)
                plt.xlabel("t")
                plt.ylabel("Number of messages received")

                plt.show()

                bBefProc = []
                mReceived = []
                bGoodProc = []
                payProc = []

            except Exception, e:
                print str(e)

        if f.startswith("performanceMixnode"):
            print "File: %s" % f
            try:
                with open(f, "rb") as infile:
                    csvR = csv.reader(infile)
                    for row in csvR:
                        bProcMix.append(float(row[0]))
                        bGoodMix.append(float(row[1]))
                        mRecvMix.append(float(row[2]))
                        payProc.append(float(row[3]))
                        hbSent.append(float(row[4]))
                        hbRec.append(float(row[5]))
                print "NUMBER OF messages processed by datagramReceive function in mixnode"
                print bProcMix
                print "NUMBER OF ROUT messages processed by datagramReceive function in mixnode"
                print bGoodMix
                print "NUMBER OF MESSAGES received (counted at datagramReceive) in mixnode"
                print mRecvMix

                plt.figure(1)
                plt.title("Mixnode")
                plt.subplot(211)
                plt.plot(bProcMix, 'b', marker='x')
                plt.plot(bGoodMix, 'r', marker='x', alpha=0.7)
                plt.plot(payProc, 'g', marker='x')
                plt.plot(mRecvMix, 'y', marker='x', alpha=0.3)
                plt.grid(True)
                plt.xlabel('t')
                plt.ylabel('Number of messages processed (mix)')
                #plt.show()

                plt.subplot(212)
                plt.plot(mRecvMix, marker='x')
                plt.grid(True)
                plt.xlabel("t")
                plt.ylabel("Number of messages received (mix)")
                plt.show()

                plt.title("Heartbeats")
                plt.plot(hbSent, 'b', marker='x')
                plt.plot(hbRec, 'r', marker='x')
                plt.grid(True)
                plt.show()

                bProcMix = []
                bGoodMix = []
                mRecvMix = []
                payProc = []
                hbSent = []
                hbRec = []

            except Exception, e:
                print str(e)

@roles("clients")
@parallel
def getMessagesSent(num):
    with settings(warn_only=True):
        local("rm -f messagesSent*.csv")
    #for i in range(int(num)):
    i = random.randrange(0, int(num))
    dirc = 'client%d'%i
    get(dirc+'/loopix/loopix/messagesSent.csv', 'messagesSent_client%d.csv'%i)


@roles("providers")
@parallel
def getProvidersProcData():
    with settings(warn_only=True):
        local("rm -f messagesReceivedSend*.csv")
    get('loopix/loopix/messagesReceivedSend.csv', 'PID/messagesReceivedSend-%s.csv'%env.host)
   

@roles("providers")
@parallel
def getLatencyProvider():
    with settings(warn_only=True):
        local("rm -f latency_provider*.csv")
    get('loopix/loopix/latency.csv', 'latency_provider%s.csv'%env.host)

@roles("mixnodes")
@parallel
def getLatencyMixnode():
    with settings(warn_only=True):
        local("rm -f latency_mixnode*.csv")
    get('loopix/loopix/latency.csv', 'latency_mixnode%s.csv'%env.host)

@parallel
def getLatency():
    execute(getLatencyProvider)
    execute(getLatencyMixnode)

def readLatency():
    latencyMixnode = []
    latencyProvider = []
    for f in os.listdir('.'):
        if f.startswith('latency_provider'):
            with open(f, 'rb') as infile:
                csvR = csv.reader(infile)
                for row in csvR:
                    latencyProvider.append(float(row[0]))
            print latencyProvider

            plt.figure(1)
            plt.title("Provider")
            
            plt.subplot(211)
            plt.plot(latencyProvider, 'b', marker='x')
            plt.ylabel('Provider Latency (s)')
            plt.grid(True)

            plt.subplot(212)
            y, bins, _ = plt.hist(latencyProvider, 20, alpha=0.5, normed=1)
            (mu, sigma) = norm.fit(latencyProvider)
            yn = mlab.normpdf(bins, mu, sigma)

            plt.plot(bins, yn, 'r--', linewidth=2)
            plt.grid(True)
            plt.show()

            latencyProvider = []

        if f.startswith('latency_mixnode'):
            with open(f, "rb") as infile:
                csvR = csv.reader(infile)
                for row in csvR:
                    latencyMixnode.append(float(row[0]))
            print latencyMixnode

            plt.figure(1)
            plt.title("Mixnode")
            
            plt.subplot(211)
            plt.plot(latencyMixnode, 'b', marker='x')
            plt.ylabel('Mixnode Latency (s)')
            plt.grid(True)

            plt.subplot(212)
            y, bins, _ = plt.hist(latencyMixnode, 20, alpha=0.5, normed=1)
            (mu, sigma) = norm.fit(latencyMixnode)
            yn = mlab.normpdf(bins, mu, sigma)

            plt.plot(bins, yn, 'r--', linewidth=2)
            plt.grid(True)
            plt.show()

            latencyMixnode = []

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

def readMessagesSent():
    for f in os.listdir('.'):
        if f.startswith('messagesSent_client'):
            print "File: ", f
            try:
                with open(f, 'rb') as infile:
                    csvR = csv.reader(infile)
                    for row in csvR:
                        print row
            except Exception, e:
                print str(e)


@roles("providers")
@parallel
def getPIDdata():
    with settings(warn_only="True"):
        local("rm -f PID/PIDcontrolVal*.csv")
    get("loopix/loopix/PIDcontrolVal.csv", "PID/PIDcontrolVal-%s.csv"%env.host)

def readPIDdata():
    for f in os.listdir('./PID'):
        if f.startswith('PIDcontrolVal'):
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

@runs_once
@roles("mixnodes", "clients", "providers")
def killPythonProcess():
    run("pkill -f *.py")


@runs_once
@parallel
def experiment_numClients(num):
    execute(start_mixnode, "True")
    execute(start_provider, "True")
    clients = get_clients()
    print "================================================"
    print clients
    print "================================================"
    execute(start_multi_client, num, "True", hosts=clients[0])
    execute(start_multi_client, num, "True", hosts=clients[1])
    execute(start_multi_client, num, "True", hosts=clients[2])
    time.sleep(900)
    execute(start_multi_client, num, "True", hosts=clients[3])
    time.sleep(900)
    execute(start_multi_client, num, "True", hosts=clients[4])
    time.sleep(900)
    execute(start_multi_client, num, "True", hosts=clients[5])
    print "Last called."


@roles("providers", "clients")
@parallel
def run_tcpdump():
    with settings(warn_only=True, remote_interrupt=True):
        assert(env.remote_interrupt)
        sudo('tcpdump udp -G 120 > tcpOut')

def rdpcap_and_close(filename, count=-1):
    """Read a pcap file and return a packet list
    count: read only <count> packets"""
    pcap_reader = PcapReader(filename)
    packets = pcap_reader.read_all(count=count)
    pcap_reader.close()
    return packets

@runs_once
def read_tcpdump(filename, flag=None):
    pkts = rdpcap_and_close(filename)

    time_zero = pkts[0].time
    for p in pkts:
        time = float(p.time - time_zero)
        packet_size = len(p) #size of packet
        payload_size = len(p.payload) #size of payload
        print p
        # if UDP in p:
        #     sequence_number = p.seq
        #     acknowledge_number = p.ack
        #     ip_src = p[IP].src
        #     ip_dst = p[IP].dst
        #     tcp_sport = p[TCP].sport
        #     tcp_dport = p[TCP].dport

@roles("clients", "providers")
@parallel
def interruptProcess():
    with settings(warn_only=True, remote_interrupt=True):
        sudo('kill -2 $(ps -e | pgrep tcpdump)')


@roles("clients", "providers")
@parallel
def get_tcpOutput():
    with settings(warn_only=True):
        local('rm -f tcpOut*')
    get('tcpOut', 'tcpOut2')



@runs_once
def exp_latency_vs_numClients():
    execute(startMultiAll, 5, "True")
    time.sleep(5405)
    execute(getLatency)
    local("mkdir latency_5")
    local("cp latency_provider*.csv latency_5")
    local("cp latency_mixnode*.csv latency_5")
    execute(killMultiAll, 5)

    print "=============================================="

    execute(startMultiAll, 10, "True")
    time.sleep(5405)
    execute(getLatency)
    local("mkdir latency_10")
    local("cp latency_provider*.csv latency_10")
    local("cp latency_mixnode*.csv latency_10")
    execute(killMultiAll, 10)

    print "=============================================="


    execute(startMultiAll, 15, "True")
    time.sleep(5405)
    execute(getLatency)
    local("mkdir latency_15")
    local("cp latency_provider*.csv latency_15")
    local("cp latency_mixnode*.csv latency_15")
    execute(killMultiAll, 15)

    print "=============================================="

    execute(startMultiAll, 20, "True")
    time.sleep(5405)
    execute(getLatency)
    local("mkdir latency_20")
    local("cp latency_provider*.csv latency_20")
    local("cp latency_mixnode*.csv latency_20")
    execute(killMultiAll, 20)

    print "=============================================="

    execute(startMultiAll, 25, "True")
    time.sleep(5405)
    execute(getLatency)
    local("mkdir latency_25")
    local("cp latency_provider*.csv latency_25")
    local("cp latency_mixnode*.csv latency_25")
    execute(killMultiAll, 25)

    print "=============================================="

    execute(startMultiAll, 30, "True")
    time.sleep(5405)
    execute(getLatency)
    local("mkdir latency_30")
    local("cp latency_provider*.csv latency_30")
    local("cp latency_mixnode*.csv latency_30")
    execute(killMultiAll, 30)

    print "=============================================="        












        
