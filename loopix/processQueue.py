from twisted.internet import reactor, task, defer, threads
import heapq
import time
import copy
from twisted.internet.defer import DeferredQueue, DeferredLock
import weakref
import csv

class ProcessQueue():

	def __init__(self):
		self.queue = []
		self.consumers = []

		self.target = 0.5

		self.Kp = 8.0 #2
		self.Ki = 3.5 #1
		self.Kd = 0.0 #5

		self.drop = 0
		self.sum_Error = 0.0
		self.timings = 0.0
		self.prev_Error = 0.0

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
		try:
			while self.consumers != [] and self.queue != []:
				d = self.consumers.pop(0)
				obj = self.queue.pop(0)
				dt = threads.deferToThread(self._process_in_thread, d, obj)
		except Exception, e:
			print str(e)

	def _process_in_thread(self, d, obj):
		inserted_time, message = obj
		start_time = time.time()
		d.callback(message)
		end_time = time.time()


		self.timings = 0 * self.timings + 1 * (start_time - inserted_time)


		# the proportional term produces an output value that is proportional to the current error value
		P = self.timings - self.target

		# the contribution from the integral term is proportional to both the magnitude of the error and the duration of the error
		I = 0.8 * self.sum_Error + 0.2 * P # the integral in a PID controller is the sum of the instantaneous error over time and gives the accumulated offset that should have been corrected previously

		# Derivative action predicts system behavior and thus improves settling time and stability of the system
		#D = P - I # the derivative of the process error is calculated by determining the slope of the error over time
		D = P - self.prev_Error

		self.prev_Error = P
		self.sum_Error = I

		self.drop = self.Kp*P + self.Ki*I + self.Kd*D
		save_drop = self.drop
		self.drop = max(0.0, self.drop)

		q_len = len(self.queue)
		del self.queue[:int(self.drop)]

		print "===== Delay: %.2f ==== Latency: %.2f ===== Estimate: %.2f =====" % (start_time - inserted_time, end_time - start_time, self.timings) 
		print "====Before queue len: %.2f ==== Queue Len: %.2f ==== Drop Len: %.2f ======" % (q_len, len(self.queue), self.drop)

		with open('PIDcontrolVal.csv', 'ab') as outfile:
			csvW = csv.writer(outfile, delimiter=',')
			data = [[save_drop]]
			csvW.writerows(data)

		with open("PID.csv", "ab") as outfile:
			csvW = csv.writer(outfile, delimiter=',')
			pid = [[P, I, D]]
			csvW.writerows(pid)

		with open("queueLen.csv", "ab") as outfile:
			csvW = csv.writer(outfile, delimiter=',')
			qlen = [[q_len, len(self.queue)]]
			csvW.writerows(qlen)

		with open("delay.csv", "ab") as outfile:
			csvW = csv.writer(outfile, delimiter=',')
			vdelay = [[(start_time - inserted_time)]]
			csvW.writerows(vdelay)


