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
from scipy.stats import norm
import matplotlib.mlab as mlab
import time
import subprocess
from scapy.all import *
import json

# ---------------------------------

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
env.key_filename = '../keys/Loopix.pem'
# ----------------------------------------LAUNCHING-FUNCTIONS------------------------------------------

#launching new instances
def ec2start(num, typ='t2.large'):
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

# Get private IP addresses of the instances

def ec2getIPs():
    local('rm -f dns_ip_mix.csv')
    local('rm -f dns_ip_user.csv')
    local('rm -f dns_ip_prv.csv')

    mixnodes = {}
    clients = {}
    providers = {}
    mix_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Mixnode"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    client_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Client"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    provider_instances = ec2.instances.filter(Filters=[{"Name":"tag:Type", "Values":["Provider"]}, {'Name' : 'instance-state-name', 'Values' : ['running']}])
    for i in mix_instances:
        mixnodes[i.public_dns_name] = i.private_ip_address
    for i in client_instances:
        clients[i.public_dns_name] = i.private_ip_address
    for i in provider_instances:
        providers[i.public_dns_name] = i.private_ip_address
    
    with open('dns_ip_mix.csv', 'ab') as outfile:
        csvW = csv.writer(outfile, delimiter=',')
        csvW.writerow(['DNS', 'IP'])
        for key in mixnodes:
            csvW.writerow([key, mixnodes[key]])
    with open('dns_ip_user.csv', 'ab') as outfile:
        csvW = csv.writer(outfile, delimiter=',')
        csvW.writerow(['DNS', 'IP'])
        for key in clients:
            csvW.writerow([key, clients[key]])
    with open('dns_ip_prv.csv', 'ab') as outfile:
        csvW = csv.writer(outfile, delimiter=',')
        csvW.writerow(['DNS', 'IP'])
        for key in providers:
            csvW.writerow([key, providers[key]])



#--------------------------------------DEPLOY-FUNCTIONS-----------------------------------------------------------
@parallel
def gitpull():
    with cd('loopix'):
        run('git pull')


@roles("mixnodes")
@parallel
def start_mixnode(branch):
    with cd("loopix/loopix"):
        run("git checkout %s" % branch)
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
def start_multi_client(num, branch):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            run("git checkout %s" % branch)
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
def start_provider(branch):
    with cd("loopix/loopix"):
        run("git checkout %s" % branch)
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
def startMultiAll(num, test="False"):
    execute(start_mixnode, test)
    execute(start_provider, test)
    execute(start_multi_client,num, test)


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
    sudo('yes | pip install sphinxmix')
    sudo('apt-get -y install htop')
    sudo('apt-get -y install tshark')
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
    sudo('yes | pip install sphinxmix')
    sudo('apt-get -y install htop')
    sudo('apt-get -y install tshark')
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
    sudo('yes | pip install sphinxmix')
    sudo('apt-get -y install htop')
    sudo('apt-get -y install tshark')
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

@roles("mixnodes", "clients", "providers")
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
    local('rm -f testMap.csv')
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc):
            with cd('loopix'):
                run("git pull")
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

    # 0 - 'start', 1 - 'middle', 2 - 'end'
    group_id = 0
    total_mixnode_number = len(mixnodes)
    stop = int(total_mixnode_number / 3)
    print "Group size: ", stop
    counter = 0
    for f in os.listdir('.'):
        if f.endswith(".bin"):
            with open(f, 'rb') as fileName:
                lines = petlib.pack.decode(fileName.read())
                print lines
                if lines[0] == "client":
                    print "LINES: ", lines
                    insertQuery = "INSERT INTO Users VALUES(?, ?, ?, ?, ?, ?)"
                    c.execute(insertQuery, [None, lines[1], lines[2], lines[3], 
                        sqlite3.Binary(petlib.pack.encode(lines[4])),
                        lines[5]])
                elif lines[0] == "mixnode":
                    insertQuery = "INSERT INTO Mixnodes VALUES(?, ?, ?, ?, ?, ?)"
                    c.execute(insertQuery, [None, lines[1], lines[2], lines[3],
                        sqlite3.Binary(petlib.pack.encode(lines[4])), group_id])
                    counter += 1
                    if counter == stop:
                        group_id += 1
                        counter = 0
                elif lines[0] == "provider":
                    insertQuery = "INSERT INTO Providers VALUES(?, ?, ?, ?, ?)"
                    c.execute(insertQuery, [None, lines[1], lines[2], lines[3],
                        sqlite3.Binary(petlib.pack.encode(lines[4]))])
                else:
                    assert False
    db.commit()

def checkDB_write():
    import petlib.pack

    sys.path += ["../loopix"]
    import databaseConnect as dc
    databaseName = "example.db"
    db = dc.connectToDatabase(databaseName)
    c = db.cursor()
    c.execute("SELECT * FROM Mixnodes")
    data = c.fetchall()
    for i in data:
        print i



#========================================GET COMMENDS============================================
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


@parallel
def getPerformance():
    execute(getPerformanceProviders)
    execute(getPerformanceMixnodes)


@roles("mixnodes")
@parallel
def getAnonimitySetMixnodes():
    with settings(warn_only=True):
        local("rm -f anonSetMixnode*.csv")
    get('loopix/loopix/anonSet.csv', 'anonSetMixnode-%s.csv'%env.host)


@roles("providers")
@parallel
def getAnonimitySetProviders():
    with settings(warn_only=True):
        local("rm -f anonSetProvider*.csv")
    get('loopix/loopix/anonSet.csv', 'anonSetProvider-%s.csv'%env.host)


@parallel
def getAnonSet():
    execute(getAnonimitySetMixnodes)
    # execute(getAnonimitySetProviders)


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
    otherProc = []
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
                        otherProc.append(float(row[4]))
                print "NUMBER OF messages processed by datagramReceive function"
                print bBefProc
                print "NUMBER OF ROUT messages processed by datagramReceive function"
                print bGoodProc
                print "NUMBER OF MESSAGES received (counted at datagramReceive)"
                print mReceived
                print "NUMBER OF ACK MESSAGES"
                print otherProc

                plt.figure(1)
                plt.subplot(211)
                plt.plot(bBefProc, 'b', marker='x')
                plt.plot(bGoodProc, 'r', marker='x', alpha=0.7)
                plt.plot(payProc, 'g', marker='x')
                plt.plot(mReceived, 'y', marker='x', alpha=0.3)
                plt.plot(otherProc, color='orange', marker='o', alpha=0.7)
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
                otherProc = []

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
                        otherProc.append(float(row[6]))
                print "NUMBER OF messages processed by datagramReceive function in mixnode"
                print bProcMix
                print "NUMBER OF ROUT messages processed by datagramReceive function in mixnode"
                print bGoodMix
                print "NUMBER OF MESSAGES received (counted at datagramReceive) in mixnode"
                print mRecvMix
                print "NUMBER OF ACK MESSAGES"
                print otherProc

                plt.figure(1)
                plt.title("Mixnode")
                plt.subplot(211)
                plt.plot(bProcMix, 'b', marker='x')
                plt.plot(bGoodMix, 'r', marker='x')
                plt.plot(payProc, 'g', marker='x')
                plt.plot(mRecvMix, 'y', marker='x')
                plt.plot(otherProc, color='orange', marker='o', alpha=0.7)
                plt.grid(True)
                plt.xlabel('t')
                plt.ylabel('Number of messages processed (mix)')

                plt.subplot(212)
                plt.plot(mRecvMix, marker='x')
                plt.grid(True)
                plt.xlabel("t")
                plt.ylabel("Number of messages received (mix)")
                plt.show()

                bProcMix = []
                bGoodMix = []
                mRecvMix = []
                payProc = []
                hbSent = []
                hbRec = []
                otherProc = []

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


@roles("providers", "clients", "mixnodes")
@parallel
def run_tcpdump(time):
    with settings(warn_only=True, remote_interrupt=True):
        run('rm -f tcpOut.pcap')
        assert(env.remote_interrupt)
        # --snapshot-length=1000
        sudo('timeout %ss tcpdump udp -w tcpOut.pcap' % str(time))

@roles("mixnodes")
@parallel
def run_tshark(time):
    #sudo('yes | dpkg-reconfigure wireshark-common')
    #sudo('yes | gpasswd -a $USER wireshark')
    with settings(warn_only=True, remote_interrupt=True):
        run('rm -f tcpOut.pcap')
        assert(env.remote_interrupt)
        run('touch tcpOut.pcap')
        sudo('chmod o=rw tcpOut.pcap')
        # sudo('tshark -n -f udp -e frame.number -e frame.time -e ip.src -e ip.dst -e udp.srcport -e udp.dstport -e udp.port -e udp.length -T fields -a duration:%s -w tcpOut.pcap' % str(time))
        sudo('tshark -n -f udp -e frame.time -e frame.time_delta -e ip.src -e ip.dst -e udp.srcport -e udp.dstport -e udp.port -e udp.length -T fields -a duration:%s -w tcpOut.pcap' % str(time))

@roles("providers")
@parallel
def get_tcpdumpOutput_provider():
    with settings(warn_only=True):
        local('rm -f tcpOut_provider*')
    get('tcpOut.pcap', 'tcpOut_provider_%s.pcap' % env.host)

@roles("clients")
@parallel
def get_tcpdumpOutput_client():
    with settings(warn_only=True):
        local('rm -f tcpOut_client*')
    get('tcpOut.pcap', 'tcpOut_client_%s.pcap' % env.host)

@roles("mixnodes")
@parallel
def get_tcpdumpOutput_mixnode():
    with settings(warn_only=True):
        local('rm -f tcpOut_mixnode*')
    get('tcpOut.pcap', 'tcpOut_mixnode_%s.pcap' % env.host)

@parallel
def get_tcpdumpOutput():
    execute(get_tcpdumpOutput_provider)
    execute(get_tcpdumpOutput_client)
    execute(get_tcpdumpOutput_mixnode)


def read_tcpOutputs():
    for f in os.listdir('.'):
        if f.startswith('tcpOut'):
            print "File: ", f
            read_tcpdump(f)

@roles("clients", "providers")
@parallel
def interruptProcess():
    with settings(warn_only=True, remote_interrupt=True):
        sudo('kill -2 $(ps -e | pgrep tcpdump)')


@roles("providers", "clients", "mixnodes")
@parallel
def take_ip():
    output = run('curl -s http://whatismijnip.nl')
    print "RESULT: ", output
    data = output.split(' ')
    print data[:-1]


def run_multiple_clients(subpath, numClients):

    for i in range(5, 101, 5):
        execute(run_clients, i)
        time.sleep(1805) 
        execute(getPerformance)
        local("mkdir performance_%d_%s" % (i, subpath))
        local("cp performanceProvider*.csv performance_%d_%s" % (i, subpath))
        local("cp performanceMixnode*.csv performance_%d_%s" % (i, subpath))
        execute(killMultiAll, i)
        execute(reset_config, int(numClients))


def update_config_file(new_rate_payload, new_rate_loops, new_rate_drop, new_mix_loop, delay):
    configFile = '../loopix/config.json'

    with open(configFile) as infile:
        _PARAMS = json.load(infile)

        _PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"] = str(new_rate_payload)
        _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = str(new_rate_loops)
        _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = str(new_rate_drop)
        _PARAMS["parametersClients"]["EXP_PARAMS_DELAY"] = str(delay)

        _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = str(new_rate_drop)
    #local('rm -f %s' % configFile)

    with open(configFile, 'w') as f:
        json.dump(_PARAMS, f, indent=4)

@roles('mixnodes', 'providers')
def upload_config_file_servers():
    put('../loopix/config.json', 'loopix/loopix/config.json')

@roles('clients')
@parallel
def upload_config_file_clients(numClients):
    for i in range(int(numClients)):
        put('../loopix/config.json', 'client%d/loopix/loopix/config.json'%i)

@runs_once
def exp_latency_vs_numClients():

    for i in range(10, 81, 10):
        execute(startMultiAll, i, "True")
        time.sleep(1805)
        execute(getLatency)
        local("mkdir latency_%d" % i)
        local("cp latency_provider*.csv latency_%d" % i)
        local("cp latency_mixnode*.csv latency_%d" % i)
        execute(killMultiAll, i)
        print "=============================================="


def experiment_increasing_payload(numClients):
    execute(reset_config, int(numClients))
    execute(update_git, int(numClients), "develop")

    configFile = '../loopix/config.json'
    with open(configFile) as infile:
        _PARAMS = json.load(infile)
        old_rate = float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"])

    C = 2.0

    for i in range(40):
        if i > 0:
            new_rate = float(60.0/((60.0/old_rate) + C))

            execute(update_config_file, new_rate)
            execute(upload_config_file, int(numClients))
            old_rate = new_rate

        execute(start_mixnode, "True")
        execute(start_provider, "True")
        execute(run_clients, int(numClients), "True")
        time.sleep(1805)
        execute(getPerformance)
        execute(getMessagesSent, int(numClients))
        execute(getLatency)
        execute(getAnonSet)
        local('mkdir performance%d_%d' % (int(numClients), i))
        local("cp performanceProvider*.csv performance%d_%d" % (int(numClients), i))
        local("cp performanceMixnode*.csv performance%d_%d" % (int(numClients), i))
        local("cp messagesSent*.csv performance%d_%d" % (int(numClients), i))
        local("cp latency_provider*.csv performance%d_%d" % (int(numClients), i))
        local("cp latency_mixnode*.csv performance%d_%d" % (int(numClients), i))
        local("cp anonSetMixnode-*.csv performance%d_%d" % (int(numClients), i))
        local("cp anonSetProvider-*.csv performance%d_%d" % (int(numClients), i))    
        execute(killMultiAll, int(numClients))
        execute(reset_config, int(numClients))


@parallel
def experiment_anonimity_set(numClients, branch):
    execute(reset_config, int(numClients))
    execute(update_git, int(numClients), branch)

    configFile = '../loopix/config.json'
    with open(configFile) as infile:
        _PARAMS = json.load(infile)
        old_rate = float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"])

    C = 2.0
    for i in range(25):
        if i > 0:
            new_rate = float(60.0/((60.0/old_rate) + C))

            execute(update_config_file, new_rate)
            execute(upload_config_file, int(numClients))
            old_rate = new_rate

        for j in range(25, 101, 25):
            execute(start_mixnode, "True")
            execute(start_provider, "True")
            execute(run_clients, j)
            time.sleep(1805)
            execute(getPerformance)
            execute(getMessagesSent, j)
            execute(getLatency)
            execute(getAnonSet)
            local("mkdir anonimitySet%d_%d" % (j, i))
            local("cp performanceProvider*.csv anonimitySet%d_%d" % (j, i))
            local("cp performanceMixnode*.csv anonimitySet%d_%d" % (j, i))
            local("cp messagesSent*.csv anonimitySet%d_%d" % (j, i))
            #local("cp latency_provider*.csv anonimitySet%d_%d" % (j, i))
            #local("cp latency_mixnode*.csv anonimitySet%d_%d" % (j, i))
            local("cp anonSetMixnode-*.csv anonimitySet%d_%d" % (j, i))
            local("cp anonSetProvider-*.csv anonimitySet%d_%d" % (j, i))
            execute(killMultiAll, j)
            execute(reset_config, int(numClients))

@roles("clients")
@parallel
def run_clients(num, branch):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            run("git checkout %s" % branch)
            run('twistd -y run_client.py')
            pid = run('cat twistd.pid')
            print "Run Client on %s with PID %s" % (env.host, pid) 

@roles("mixnodes", "providers")
def reset_config_servers(branch):
    with cd("loopix/loopix"):
        run("git checkout %s" % branch)
        run('git reset --hard')

@roles("clients")
@parallel
def reset_config_clients(num, branch):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            #sudo('rm -f config.json')
            run("git checkout %s" % branch)
            run('git reset --hard')


@roles("mixnodes", "providers")
@parallel
def update_git_servers(branch):
    with cd("loopix/loopix"):
        run("git checkout %s" % branch)
        run("git pull")
    
@roles("clients")
@parallel
def update_git_clients(num, branch):
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            run("git checkout %s" % branch)
            run('git pull')
    
def update_git(numClients, branch):
    execute(update_git_servers, branch)
    execute(update_git_clients, int(numClients), branch)


@parallel
def experiment_tcpDump(num):
    execute(startMultiAll, int(num), "True")
    time.sleep(60)
    execute(run_tcpdump, 120)
    execute(get_tcpdumpOutput)
    execute(getAnonSet)
    execute(killMultiAll, int(num))

@parallel
def measureAnonSet(lambda_p, lambda_l, lambda_d, lambda_m, delay, num, flagId=1):
    configFile = '../loopix/config.json'

    execute(reset_config_clients, int(num), "develop")
    execute(reset_config_servers, "develop")
    
    execute(update_git, int(num), "develop")
    execute(update_config_file, lambda_p, lambda_l, lambda_d, lambda_m, delay)
    execute(upload_config_file_clients, int(num))
    execute(upload_config_file_servers)

    execute(start_mixnode, "True")
    execute(start_provider, "True")
    execute(run_clients, int(num), "True")
    time.sleep(600)
    execute(run_tcpdump, 300)
    execute(get_tcpdumpOutput)
    execute(getAnonSet)
    local("mkdir measurments%d_%d" % (int(num), flagId))
    local("cp tcpOut_provider*.pcap measurments%d_%d" % (int(num), flagId))
    local("cp tcpOut_mixnode*.pcap measurments%d_%d" % (int(num), flagId))
    local("cp tcpOut_client*.pcap measurments%d_%d" % (int(num), flagId))
    local("cp anonSetMixnode-*.csv measurments%d_%d" % (int(num), flagId))
    local("cp anonSetProvider-*.csv measurments%d_%d" % (int(num), flagId))
    execute(killMultiAll, int(num))
    execute(reset_config_clients, int(num), "develop")
    execute(reset_config_servers, "develop")

    
@roles("mixnodes")
@parallel
def start_sphinx_mixnode():
    sudo('yes | pip install sphinxmix')
    with cd("loopix/loopix"):
        run("git fetch")
        run("git checkout sphinx")
        run("git pull")
        run("twistd -y run_mixnode.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)

@roles("providers")
@parallel
def start_sphinx_provider():
    sudo('yes | pip install sphinxmix')
    with cd("loopix/loopix"):
        run("git fetch")
        run("git checkout sphinx")
        run("git pull")
        run("twistd -y run_provider.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)

@roles("clients")
@parallel
def start_sphinx_client(num):
    sudo('yes | pip install sphinxmix')
    for i in range(int(num)):
        dirc = 'client%s' % i
        with cd(dirc+'/loopix/loopix'):
            run("git fetch")
            run("git checkout sphinx")
            run('git pull')
            run('twistd -y run_client.py')
            pid = run('cat twistd.pid')
            print "Run Client on %s with PID %s" % (env.host, pid) 

@parallel    
def test_sphinx_packet(num):
    execute(start_sphinx_mixnode)
    execute(start_sphinx_provider)
    execute(start_sphinx_client, int(num))
    #execute(run_tshark,120)
    #time.sleep(200)
    #execute(get_tcpdumpOutput_mixnode)
    #time.sleep(900)
    #execute(getAnonSet)
    #execute(getPerformance)

@roles('mixnodes')
@parallel
def run_mixnode(branch):
    with cd('loopix/loopix'):
        # run("git checkout %s" % branch)
        run("twistd -y run_mixnode.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)

@roles('providers')
@parallel
def run_provider(branch):
    with cd('loopix/loopix'):
        # run("git checkout %s" % branch)
        run("twistd -y run_provider.py")
        pid = run("cat twistd.pid")
        print "Run on %s with PID %s" % (env.host, pid)




# ==============================================================================


@runs_once
def exp_Loopix_sec_params(mixnodes, providers, clients):
    execute(ec2start_mixnode_instance, int(mixnodes))
    execute(ec2start_provider_instance, int(providers))
    execute(ec2start_client_instance, int(clients))

@runs_once
def ec2stop_experiment():
    execute(ec2stopAll)


@parallel
def exp_setup(client):
    execute(setupServers)
    execute(setupClients, int(client))

@runs_once
def exp_deploy(clients):
    with settings(warn_only=True):
        local("rm *.bin *.bi2 example.db")
    execute(deployMixnode)
    execute(deployProvider)
    execute(storeProvidersNames)
    execute(deployMultiClient,int(clients))
    execute(readFiles)
    execute(loaddirServers)
    execute(loaddirClients,int(clients))

def read_in_mapping():
    mapping = {}
    with open('testMap.csv', 'r') as infile:
        csvR = csv.reader(infile)
        for row in csvR:
            mapping[row[0]] = row[1]
    print mapping
    return mapping

def run_client_id(clientId):
    mapping = read_in_mapping()
    dirc = mapping[clientId]
    print 'Client under directory ', dirc
    with cd(dirc+'/loopix/loopix'):
            run("git checkout %s" % branch)
            run('git pull')
            run('twistd -y run_client.py')
            pid = run('cat twistd.pid')
            print "Run Client on %s with PID %s" % (env.host, pid)


@roles("clients")
@parallel
def upload_to_dirc(fileName, dirc):
    # put('../loopix/%s' % fileName, '%s/loopix/loopix/%s'%(dirc, fileName))
    put('../loopix/config.json', '%s/loopix/loopix/config.json'%dirc)


@roles("clients")
@parallel
def run_client_id(dirc, branch):
    with cd(dirc+'/loopix/loopix'):
        run("git checkout %s" % branch)
        run('twistd -y run_client.py')
        pid = run('cat twistd.pid')
        print "Run Client on %s with PID %s" % (env.host, pid) 

# @roles("clients")
# @parallel
# def run_clients(num, branch):
#     for i in range(int(num)):
#         dirc = 'client%s' % i
#         with cd(dirc+'/loopix/loopix'):
#             run("git checkout %s" % branch)
#             run('twistd -y run_client.py')
#             pid = run('cat twistd.pid')
#             print "Run Client on %s with PID %s" % (env.host, pid) 

# ================================================================================================ 
@parallel
def exp_test(clients, loopsOn=False, dropOn = False, loopClientParam=None, dropClientParam=None, loopMixParam=None):
    
    configFile = '../loopix/config.json'

    execute(reset_config_clients, int(clients), 'sphinx')
    execute(reset_config_servers, 'sphinx')
    execute(update_git_clients, int(clients), 'sphinx')
    execute(update_git_servers, 'sphinx')
    
    mapping = read_in_mapping()

    # ---------------------------SETTING UP MIXNODES AND PROVIDERS--------------------
    if not loopsOn:
        with open(configFile) as infile:
            _PARAMS = json.load(infile)
            _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = "None"
        with open(configFile, 'w') as outfile:
            json.dump(_PARAMS, outfile, indent=4)
    else:
        with open(configFile) as infile:
            _PARAMS = json.load(infile)
            _PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"] = str(loopMixParam)
        with open(configFile, 'w') as outfile:
            json.dump(_PARAMS, outfile, indent=4)

    # uploading config file for servers (mixnodes and providers)
    execute(upload_config_file_servers)

    # ---------------------------------------------------------------------------------
    data = read_from_db('example.db', 'Users')
    tS, tR = random.sample(data, 2)
    print "SENDER: ", tS
    print "RECEIVER: ", tR

    with open(configFile) as infile:
        _PARAMS = json.load(infile)
        _PARAMS["parametersClients"]["TARGETUSER"] = "True"
        _PARAMS["parametersClients"]["TESTMODE"] = "True"
        _PARAMS["parametersClients"]["FAKE_MESSAGING"] = "False"
        if not loopsOn:
            _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = "None"
        else:
            _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = str(loopClientParam)
        if not dropOn:
            _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = "None"
        else:
            _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = str(dropClientParam)
    with open(configFile, 'w') as f:
        json.dump(_PARAMS, f, indent=4)

    senderId = tS[1]
    dircS = mapping[senderId]
    execute(upload_to_dirc, 'configFile.json', dircS)

    # setting up usuall clients
    with open(configFile) as infile:
        _PARAMS = json.load(infile)
        _PARAMS["parametersClients"]["TARGETUSER"] = "False"
        _PARAMS["parametersClients"]["TESTMODE"] = "True"
        _PARAMS["parametersClients"]["FAKE_MESSAGING"] = "False"
        if not loopsOn:
            _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] = "None"
        if not dropOn:
            _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] = "None"
    with open(configFile, 'w') as f:
        json.dump(_PARAMS, f, indent=4)

    receiverId = tR[1]
    dircR = mapping[receiverId]
    execute(upload_to_dirc, 'configFile.json', dircR)

    execute(run_mixnode, 'sphinx')
    execute(run_provider, 'sphinx')
    execute(run_client_id, dircS, 'sphinx')
    execute(run_client_id, dircR, 'sphinx')

    print "Sender - Receiver", (dircS, dircR)
    execute(run_tshark, 300)
    time.sleep(400)
    execute(get_tcpdumpOutput_mixnode)

    execute(killMultiAll, int(clients))
    # reset changes to avoid git commit
    execute(reset_config_clients, int(clients), 'sphinx')
    execute(reset_config_servers, 'sphinx')
    execute(update_git_clients, int(clients), 'sphinx')
    execute(update_git_servers, 'sphinx')


@parallel
def exp_run(case, population=10, loopsOn=False):
    if case == '1':
        execute(exp_unobservability, 1, 1, loopsOn)
    if case == '2':
        execute(exp_unobservability, int(population), 1, loopsOn)


@runs_once
def read_from_db(databaseName, tableName):
    sys.path += ["../loopix"]
    import databaseConnect as dc

    db = dc.connectToDatabase(databaseName)
    c = db.cursor()
    c.execute("SELECT * FROM %s" % tableName)
    data = c.fetchall()
    return data

def take_random_client():
    data = read_from_db('example.db', 'Users')
    for d in data:
        print d
    c = random.choice(data)
    return c










        
