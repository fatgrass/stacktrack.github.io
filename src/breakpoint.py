'''

# This file contains python code to be imported into gdb, this can be done
# using the following gdb commands
# "VM" is a virtual machine which is beig debugged


set pagination off                  # Disable paging
target remote VM:8864               # Connect to the vm, execution will be paused

python
breakpoint.del_bps()                # Delete any breakpoints
end

python
import breakpoint, importlib        #
importlib.reload(breakpoint)        # reload any changes to this file
load('sys_chdir')                   # load the graph from the xref db 
breakpoint.STBreakpoint('sys_chdir')# put a breakpoint on the sys_chdir syscall so we can trace it
end                                 #

continue                            # continue execution

python                              #
STBreakpoint.graph.dump_nodes('.')  # dump the json trace to the current directory
end                                 #

'''

import gdb
import linux
import sys
import MySQLdb as mdb
import json
import signal
from Graph import *

SLAVE_PROCESS_NAME='trinity-'
graph = Graph()
OUT_DIR='/var/u'

def load(symbol):

    def sig_handler(signum, frame):
        # Handler to dump graphs in case tracer is stuck
        print('received signal, dumping graphs')
        dump_graphs()

    node = graph.add_node(symbol)
    print('loading {}'.format(node))
    graph.load(load_callers = False, load_callees = True)
    print('register signal handler')
    # signal.SIGRTMAX = 64
    signal.signal(signal.SIGRTMAX, sig_handler)

def get_callees(symbol):
    return  graph.xrefdb.get_callees(symbol)

def del_bps(start=None,end=None):
    for bp in gdb.breakpoints():
        bp.delete()

def get_current():
    lxc=linux.cpus.LxCurrentFunc()
    return lxc.invoke()

def get_bt_start():
    fend = ''
    try:
        backtrace = gdb.execute('backtrace', to_string = True)
        # 
        # #4  0xffffffff817be132 in entry_SYSCALL_64_fastpath
        f_end    = backtrace.split('\n')[-3].split(' ')[2]
        print(backtrace)
        print('fend: {}'.format(f_end))
        EndBreakPoint(f_end)
    except:
        print("get_bt_start failed, backtrace:")
        print(f_end)

def dump_graphs():
    print("Dumping Graphs")
    graph.dump_nodes(OUT_DIR)
    STBreakpoint.graph.dump_nodes(OUT_DIR,suffix='-trace')

class EndBreakPoint(gdb.Breakpoint):
    
    def __init__(self,address):
        func_name = '*' + address
        print('ENDBP at '+ func_name) 
        super(EndBreakPoint, self).__init__(
            func_name, gdb.BP_BREAKPOINT, internal=False
        )

    def stop(self):
        comm = get_current()['comm'].string()
        if not comm.startswith(SLAVE_PROCESS_NAME):
            return
        print('Finalizing trace')
        dump_graphs()
        for bp in gdb.breakpoints():
            if bp == self:
                bp.enabled = False
            else:
                bp.delete()
        print('Done -- detach & quit')
        gdb.execute('detach')
        gdb.execute('quit')


class STBreakpoint(gdb.Breakpoint):

    bplist   = set()
    todelete = []
    edges    = []
    graph    = Graph()

    def __init__(self, func_name, parent=None):

        self.func_name = func_name        
        # node = self.node      = self.graph.add_node(func_name)
        # if not node in self.graph.nodes: self.graph.load_node(self.node)
        self.parent    = parent
        STBreakpoint.bplist.add(func_name)
        #print('ini %s'%str(func_name))
        super(STBreakpoint, self).__init__(
            func_name, gdb.BP_BREAKPOINT, internal=False
        )
 
    def _stop(self):
        comm = get_current()['comm'].string()
        if not comm.startswith(SLAVE_PROCESS_NAME):
            return
        print(self.func_name)

    def stop(self):
        comm = get_current()['comm'].string()
        if not comm.startswith(SLAVE_PROCESS_NAME):
            return
       
        if self.parent:
            STBreakpoint.graph.add_edge(self.parent,self.func_name)
        else:
            get_bt_start()


        for bp in STBreakpoint.todelete:
            try:
                if bp.func_name != self.func_name:
                    bp.delete()
            except:
                pass
      
        for callee in get_callees(self.func_name):
            if callee not in STBreakpoint.bplist:
                STBreakpoint(callee,self.func_name)

        STBreakpoint.todelete += [self]
        

