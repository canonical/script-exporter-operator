#!/bin/sh
echo "# HELP hello world"
echo "# TYPE hello_world gauge"
echo "hello_world{param=\"$1\"} 1"
