from fabric.api import env, sudo, run, settings, cd, local
from fabric.decorators import runs_once, roles, parallel
from fabric.tasks import execute 

@runs_once
def package():
	local("python setup.py sdist")