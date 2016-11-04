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
		print "Process Queue: Called get"
		d = defer.Deferred()
		self.consumers += [d]

		reactor.callLater(0.0, self._process)
		return d

	def _process(self):
		print "--- Called _process in ProcessQueue file"
		try:
			#self._lock.acquire()
			while self.consumers != [] and self.queue != []:
				d = self.consumers.pop(0)
				obj = self.queue.pop(0)
				dt = threads.deferToThread(self._process_in_thread, d, obj)
			#self._lock.release()
		except Exception, e:
			print str(e)

	def _process_in_thread(self, d, obj):
		print "---- Called process in thread in ProcessQueue ------"
		d.callback(obj)
	


