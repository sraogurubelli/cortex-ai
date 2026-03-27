#!/bin/bash
echo "DEBUG: Hook was triggered!" >> /tmp/claude-hook-debug.log
echo "DEBUG: Timestamp: $(date)" >> /tmp/claude-hook-debug.log
echo "DEBUG: Input received" >> /tmp/claude-hook-debug.log
cat >> /tmp/claude-hook-debug.log
