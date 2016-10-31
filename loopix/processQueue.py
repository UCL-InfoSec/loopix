from twisted.internet import reactor, task, defer, threads
import heapq
import time

class ProcessQueue():

	def __init__(self):
		self.queue = []
		self.consumers = []

	def put(self, obj):
		self.queue.append(obj)

	def get(self):
		d = defer.Deferred()
		self.consumers += [d]

		reactor.callLater(0.5, self._process)
		return d

	def _process(self):
		while self.consumers != [] and self.queue != []:
			d = self.consumers.pop(0)
			obj = self.queue.pop(0)
			dt = threads.deferToThread(self._process_in_thread, d, obj)

	def _process_in_thread(self, d, obj):
		d.callback(obj)
	


