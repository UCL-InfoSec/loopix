from twisted.internet import reactor, task, defer, threads
import heapq
import time
import copy
from twisted.internet.defer import DeferredQueue, DeferredLock
import weakref

class ProcessQueue():

	def __init__(self):
		self.queue = []
		self.consumers = []

		self.target = 0.02

		self.Kp = 2.0
		self.Ki = 1.0
		self.Kd = 5.0

		self.drop = 0
		self.sum_Error = 0.0
		self.timings = 0.0

	def put(self, obj):
		insert_t = time.time()
		self.queue.append((insert_t, obj))

		self._process()

	def get(self):
		d = defer.Deferred()
		self.consumers += [d]

		reactor.callLater(0.0, self._process)
		return d

	def _process(self):
		#print "--- Called _process in ProcessQueue file"
		try:
			while self.consumers != [] and self.queue != []:
				d = self.consumers.pop(0)
				obj = self.queue.pop(0)
				dt = threads.deferToThread(self._process_in_thread, d, obj)
		except Exception, e:
			print str(e)

	def _process_in_thread(self, d, obj):
		#print "---- Called process in thread in ProcessQueue ------"
		inserted_time, message = obj
		start_time = time.time()
		d.callback(message)
		end_time = time.time()

		self.timings = 0.5*self.timings + 0.5 * (start_time - inserted_time)

		P = self.timings - self.target
		I = 0.8 * self.sum_Error + 0.2 * P
		D = P - I
		self.prev_Error = P
		self.sum_Error = I

		self.drop += self.Kp*P + self.Ki*I + self.Kd*D
		self.drop = max(0.0, self.drop)

		del self.queue[:int(self.drop)]

		print "===== Delay: %.2f ==== Latency: %.2f ===== Estimate: %.2f =====" % (start_time - inserted_time, end_time - start_time, self.timings) 
		print "==== Queue Len: %.2f ==== Drop Len: %.2f ======" % (len(self.queue), self.drop)
	
