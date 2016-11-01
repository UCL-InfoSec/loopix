from twisted.internet import reactor, task, defer, threads
import heapq
import time
import copy
from twisted.internet.defer import DeferredQueue, DeferredLock

class ProcessQueue():

	def __init__(self):
		self.queue = []
		self.consumers = []

		self._lock = DeferredLock()

	def put(self, obj):
		self.queue.append(obj)
		#print "Current size PUT: ", len(self.queue)

	def get(self):
		d = defer.Deferred()
		self.consumers += [d]

		reactor.callLater(1, self._process)
		return d

	def _process(self):

		self._lock.acquire()
		while self.consumers != [] and self.queue != []:
			d = self.consumers.pop(0)
			obj = self.queue.pop(0)
			dt = threads.deferToThread(self._process_in_thread, d, copy.deepcopy(obj))
		self._lock.release()

	def _process_in_thread(self, d, obj):
		print "PROCESS IN THREAD"
		d.callback(copy.deepcopy(obj))
	


