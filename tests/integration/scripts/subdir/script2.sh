#!/bin/sh
echo "# HELP hello world"
echo "# TYPE hello_world gauge"
echo "bye_world{param=\"$1\"} 1"
