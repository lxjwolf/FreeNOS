#
# Copyright (C) 2015 Niek Linnenbank
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from SCons.Script import *
import subprocess
import multiprocessing
import shlex
import sys
import os
import os.path
import time

def timeoutChecker(proc, timeout):
    time.sleep(timeout)
    print "Timeout occured (" + str(timeout) + " sec) -- aborting"
    proc.terminate()
    sys.exit(1)

def writeTap(testname, data, env):
    """
    Write TAP test output
    """
    outfile = env['BUILDROOT'] + '/tap/' + testname + '.tap'

    try:
        os.makedirs(os.path.dirname(outfile))
    except Exception as e:
        pass

    f = open(outfile, 'w')
    f.write(data)
    f.close()

def runTester(target, source, env):
    """
    Run the FreeNOS autotester and collect TAP results.
    """

    # Needed to workaround SCons problem with the pickle module.
    # See: http://stackoverflow.com/questions/24453387/scons-attributeerror-builtin-function-or-method-object-has-no-attribute-disp
    import imp

    del sys.modules['pickle']
    del sys.modules['cPickle']

    sys.modules['pickle'] = imp.load_module('pickle', *imp.find_module('pickle'))
    sys.modules['cPickle'] = imp.load_module('cPickle', *imp.find_module('cPickle'))

    import pickle
    import cPickle

    cmd = str(env['TESTCMD'])
    cmd = env.subst(cmd)

    # Launch process
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    # Launch a timeout process which will send a SIGTERM
    # to the process after a certain amount of time
    ch = multiprocessing.Process(target = timeoutChecker, args=(proc, 60 * 3))
    ch.start()

    # When running from the FreeNOS interactive console, first wait for
    # the /bin/login prompt and give the login input values. After that,
    # start the autotester.
    if 'TESTPROMPT' in env:
        output=""
        while True:
            c = proc.stdout.read(1)
            if c == '':
                break

            sys.stdout.write(c)
            sys.stdout.flush()
            output += c

            if env['TESTPROMPT'] in output:
                proc.stdin.write("root\n/test/run /test --tap\n")
                proc.stdin.flush()
                break

    # Buffer TAP output
    tap=""

    while True:
        line = proc.stdout.readline()
        if line == '':
            break

        line = line.strip()

        sys.stdout.write(line + os.linesep)
        sys.stdout.flush()

        if line.startswith('# Finish') and line.endswith('/test/run'):
            proc.terminate()
            ch.terminate()
            return

        elif "# Start" in line:
            tap=line + "\n"

        elif line.startswith("# Finish"):
            writeTap(line[9:], tap, env)
            tap=""
        else:
            tap += line + "\n"

    print "Unexpected end of test output"
    proc.terminate()
    ch.terminate()
    sys.exit(1)

def setupTester(env, **kw):

    # Make sure to pass the whole environment to the command.
    env.Append(ENV = os.environ)

    # Register SCons builder which always needs to run
    for target,action in kw.items():
        env.Append(TESTCMD = str(action))
        env.AlwaysBuild(env.Alias(target, [], runTester))

#
# Run the FreeNOS autotester inside qemu
#
def AutoTester(env, **kw):
    if not env:
        env = DefaultEnvironment()
    else:
        env = env.Clone()

    env.SetDefault(TESTPROMPT="\nlogin: ")
    setupTester(env, **kw)

#
# Run FreeNOS autotester in a host OS local process
#
def LocalTester(env, **kw):
    if not env:
        env = DefaultEnvironment()
    else:
        env = env.Clone()

    setupTester(env, **kw)

#
# Add ourselves to the given environment.
#
def generate(env):
    env.AddMethod(AutoTester)
    env.AddMethod(LocalTester)

#
# We always exist.
#
def exists(env):
    return True
