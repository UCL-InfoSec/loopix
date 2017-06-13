import os.path
import sqlite3
import petlib.pack
import pytest
from support_formats import Mix, Provider, User

class DatabaseManager(object):
    def __init__(self, databaseName):
        self.db = sqlite3.connect(databaseName)
        self.cursor = self.db.cursor()

    def create_users_table(self, table_name):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY,
                            name blob,
                            port integer,
                            host text,
                            pubk blob,
                            provider blob)'''%table_name)
        self.db.commit()
        print "Table [%s] created succesfully." % table_name

    def create_providers_table(self, table_name):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY,
                            name blob,
                            port integer,
                            host text,
                            pubk blob)'''%table_name)
        self.db.commit()
        print "Table [%s] created succesfully." % table_name

    def create_mixnodes_table(self, table_name):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY,
                            name blob,
                            port integer,
                            host text,
                            pubk blob,
                            groupId integer)'''%table_name)
        self.db.commit()
        print "Table [%s] created succesfully." % table_name

    def drop_table(self, table_name):
        self.cursor.execute("DROP TABLE IF EXISTS %s"%table_name)
        print "Tabel [%s] droped succesfully." % table_name

    def insert_row_into_table(self, table_name, params):
        insert_query = "INSERT INTO %s VALUES (%s)" % (table_name, ', '.join('?' for p in params))
        self.cursor.execute(insert_query, params)
        self.db.commit()

    def select_all(self, table_name):
        self.cursor.execute("SELECT * FROM %s" % table_name)
        return self.cursor.fetchall()

    def select_all_mixnodes(self):
        mixes_info = self.select_all('Mixnodes')
        mixes = []
        for mix in mixes_info:
            mixes.append(Mix(mix[1], mix[2], mix[3], petlib.pack.decode(mix[4]), mix[5]))
        return mixes

    def select_all_providers(self):
        providers_info = self.select_all('Providers')
        providers = []
        for prv in providers_info:
            providers.append(Provider(str(prv[1]), prv[2], str(prv[3]), petlib.pack.decode(prv[4])))
        return providers

    def select_all_clients(self):
        clients_info = self.select_all('Users')
        clients = []
        for client in clients_info:
            provider = self.select_provider_by_name(client[5])
            clients.append(User(str(client[1]), client[2], client[3], petlib.pack.decode(client[4]), provider))
        return clients

    def select_provider_by_name(self, param_val):
        self.cursor.execute("SELECT * FROM Providers WHERE name = ?", [str(param_val)])
        plist = self.cursor.fetchone()
        return Provider(str(plist[1]), plist[2], str(plist[3]), petlib.pack.decode(plist[4]))

    def count_rows(self, table_name):
        self.cursor.execute("SELECT Count(*) FROM %s" % table_name)
        return int(self.cursor.fetchone()[0])

    def close_connection(self):
        self.db.close()



if os.path.isfile('testdb.db'):
    os.remove('testdb.db')

def test_init():
    manager = DatabaseManager('testdb.db')
    return manager

db_manager = test_init()

def test_create_users_table():
    db_manager.create_users_table('Table_Users')
    db_manager.cursor.execute("SELECT count(*) FROM sqlite_master  \
                            WHERE type='table' AND name='Table_Users';")
    assert db_manager.cursor.fetchone()[0] == 1

def test_create_providers_table():
    db_manager.create_providers_table('Table_Providers')
    db_manager.cursor.execute("SELECT count(*) FROM sqlite_master \
                            WHERE type='table' AND name='Table_Providers';")
    assert db_manager.cursor.fetchone()[0] == 1

def test_create_mixnodes_table():
    db_manager.create_mixnodes_table('Table_Mixnodes')
    db_manager.cursor.execute("SELECT count(*) FROM sqlite_master \
                            WHERE type='table' AND name='Table_Mixnodes';")
    assert db_manager.cursor.fetchone()[0] == 1

def test_drop_table():
    db_manager.drop_table('Table_Users')
    db_manager.cursor.execute("SELECT count(*) FROM sqlite_master \
                            WHERE type='table' AND name='Table_Users';")
    assert db_manager.cursor.fetchone()[0] == 0

def test_insert_row_into_table():
    params = [None, 'Test', 1234, '1.2.3.4', '0000', 1]
    db_manager.insert_row_into_table('Table_Mixnodes', params)
    data = db_manager.select_all('Table_Mixnodes')
    assert data[0][1:] == ('Test', 1234, '1.2.3.4', '0000', 1)

def test_count_rows():
    assert db_manager.count_rows('Table_Mixnodes') == 1
