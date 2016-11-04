from twisted.internet import reactor, task, defer, threads
import heapq
import time
import copy
from twisted.internet.defer import DeferredQueue, DeferredLock
import weakref

class ProcessQueue():

	def __init__(self, parent):
		self.queue = []
		self.consumers = []


	def put(self, obj):
		self.queue.append(obj)
		print "Putting to the queue."
		
		self._process()

	def get(self):
		print "Process Queue: Called get"
		d = defer.Deferred()
		self.consumers += [d]

		reactor.callLater(0.0, self._process)
		return d

	def _process(self):
		print "--- Called _process in ProcessQueue file"
		try:
			while self.consumers != [] and self.queue != []:
				d = self.consumers.pop(0)
				obj = self.queue.pop(0)
				dt = threads.deferToThread(self._process_in_thread, d, obj)
		except Exception, e:
			print str(e)

	def _process_in_thread(self, d, obj):
		print "---- Called process in thread in ProcessQueue ------"
		d.callback(obj)
	


