import numpy
import os
import time

def generateRandomNoise(length):
    return numpy.random.bytes(length)

def sampleFromExponential((lambdaParam, size)):
    return numpy.random.exponential(lambdaParam, size)

def epoch():
	""" Function returns the current epoch time."""
	return time.time()