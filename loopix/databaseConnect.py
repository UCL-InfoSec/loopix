import sqlite3
from format3 import Mix, Provider, User
import petlib.pack
import pytest

class DatabaseManager(object):
	def __init__(self, databaseName):
		self.db = sqlite3.connect(databaseName)
		self.cursor = self.db.cursor()

	def create_users_table(self, tableName):
		self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name blob, port integer, host text, pubk blob, provider blob)'''%tableName)
		self.db.commit()
		print "Table [%s] created succesfully." % tableName

	def create_providers_table(self, tableName):
		self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name blob, port integer, host text, pubk blob)'''%tableName)
		self.db.commit()
		print "Table [%s] created succesfully." % tableName

	def create_mixnodes_table(self, tableName):
		self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name blob, port integer, host text, pubk blob, groupId integer)'''%tableName)
		self.db.commit()
		print "Table [%s] created succesfully." % tableName

	def dropTabel(self, tableName):
		self.cursor.execute("DROP TABLE IF EXISTS %s"%tableName)
		print "Tabel [%s] droped succesfully." % tableName

	def insertRowIntoTable(self, tableName, params):
		insertQuery = "INSERT INTO %s VALUES (%s)" % (tableName, ', '.join('?' for p in params))
		self.cursor.execute(insertQuery, params)
		self.db.commit()

	def selectAll(self, tableName):
		self.cursor.execute("SELECT * FROM %s" % tableName)
		return self.cursor.fetchall()

	def selectByIdx(self, tableName, idx):
		self.cursor.execute("SELECT * FROM %s WHERE id=%d" % (tableName, idx))
		return self.cursor.fetchone()

	def select_all_mixnodes(self):
		mixesInfo = self.selectAll('Mixnodes')
		mixes = []
		for m in mixesInfo:
			mixes.append(Mix(m[1], m[2], m[3], petlib.pack.decode(m[4]), m[5]))
		return mixes

	def select_all_providers(self):
		providersInfo = self.selectAll('Providers')
		providers = []
		for p in providersInfo:
			providers.append(Provider(str(p[1]), p[2], str(p[3]), petlib.pack.decode(p[4])))
		return providers

	def select_all_clients(self):
		clientsInfo = self.selectAll('Users')
		clients = []
		for c in clientsInfo:
			provider = Provider(*petlib.pack.decode(c[5]))
			clients.append(User(str(c[1]), c[2], c[3], petlib.pack.decode(c[4]), provider))
		return clients

	def countRows(self, tableName):
		self.cursor.execute("SELECT Count(*) FROM %s" % tableName)
		return int(self.cursor.fetchone()[0])

	def close_connection(self):
		self.db.close()



import os.path
if os.path.isfile('testdb.db'):
    os.remove('testdb.db')

def test_init():
	dbManager = DatabaseManager('testdb.db')
	return dbManager

dbManager = test_init()

def test_createUsersTable():
	dbManager.create_users_table('Table_Users')
	dbManager.cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='Table_Users';")
	assert dbManager.cursor.fetchone()[0] == 1

def test_createProvidersTable():
	dbManager.create_providers_table('Table_Providers')
	dbManager.cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='Table_Providers';")
	assert dbManager.cursor.fetchone()[0] == 1

def test_createMixnodesTable():
	dbManager.create_mixnodes_table('Table_Mixnodes')
	dbManager.cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='Table_Mixnodes';")
	assert dbManager.cursor.fetchone()[0] == 1

def test_dropTable():
	dbManager.dropTabel('Table_Users')
	dbManager.cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='Table_Users';")
	assert dbManager.cursor.fetchone()[0] == 0

def test_insertRowIntoTable():
	import petlib.pack
	params = [None, 'Test', 1234, '1.2.3.4', '0000', 1]
	dbManager.insertRowIntoTable('Table_Mixnodes', params)
	data = dbManager.selectAll('Table_Mixnodes')
	assert data[0][1:] == ('Test', 1234, '1.2.3.4', '0000', 1)

def test_selectByIdx():
	data = dbManager.selectByIdx('Table_Mixnodes', 1)
	assert data == (1, 'Test', 1234, '1.2.3.4', '0000', 1)

def test_countRows():
	assert dbManager.countRows('Table_Mixnodes') == 1
