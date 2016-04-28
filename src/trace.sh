#!/bin/bash
#
# This script creates a trace as follows:
#   - Reset the VM snapshot
#   - create gdb command files to be run on the master and the slave (VM)
#   - start gdb on the master
#   - ssh to the slave and start the test (trace-slave.sh)
#
# The gdb session on the master will set a breakpoint on SYSCALL (argv[1]).
# The ssh session to the client starts the program in a gdb wrapper (trace-slave.sh) 
# When the breakpoint is hit by the program on the slave, nodes are added to
# the trace. When the program exits, the nodes are dumped.
#
# /mnt/t is a directory on the master which is mounted on the same location on the slave
#

try(){
    "$@"
    if [[ $? != 0 ]]; then
        echo "Command failure: $@"
        exit 1
    fi
}

set -x

SYSCALL=$1 # The syscall to be traced
VM=192.168.122.10
SHARE=/mnt/t # Share mounted on same location on master and slave
TIMEOUT=1500
SNAPSHOT="tvm-0"

if [[ -z $SYSCALL ]]
then
    echo no syscall
    exit 1
fi

echo "Starting trace of $SYSCALL"
echo "Reverting snapshot"
try virsh snapshot-revert tvm "$SNAPSHOT"

GDBCMDS_MASTER=$(mktemp)
GDBCMDS_SLAVE=$SHARE/gdbcmds-slave

# Create master and slave gdb command files for the syscall being traced
try sed -e "s/_SYSCALL_/sys_$SYSCALL/g" gdbcmds > $GDBCMDS_MASTER
try sed -e "s/_SYSCALL_/$SYSCALL/g" gdbcmds-slave > $GDBCMDS_SLAVE

#
echo "Start the kernel gdb session"
gdb -q -x $GDBCMDS_MASTER & 
PID_GDB=$!

#
echo "Wait until kernel breakpoints are set and ssh to the slave to execute the slave test program"
sleep 20
ssh root@$VM $SHARE/trace-slave.sh &
PID_SSH=$!

# Kill all subprocesses if the trace is killed
trap "kill -9 -P $$" SIGINT SIGTERM SIGKILL

# Loop TIMEOUT seconds OR until gdb session is finished
for i in $(seq $TIMEOUT)
do
    ps -p $PID_GDB > /dev/null 2>&1 || break 
    ps -p $PID_SSH > /dev/null 2>&1 || break
    sleep 1
done

# Wait to give gdb a chance to finish cleanly, then kill the trace
# if it takes too long but first dump the graphs by sending signal nr. 64
ps -p $PID_GDB && ( 
    sleep 10 
    kill -64 $PID_GDB
    sleep 10 
    kill -9 $PID_GDB $PID_SSH ) 2>/dev/null

# Cleanup
rm -f $GDBCMDS_MASTER $GDBCMDS_SLAVE
