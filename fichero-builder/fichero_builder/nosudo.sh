#!/bin/sh
# [jail].enabled = false (builder.client.jail-optional): stands in for sudo. Drops sudo's own options (-n, -H, -u <user>)
# and runs the rest as the invoking user: nothing is elevated and no other user is reached.
while [ $# -gt 0 ]; do
  case "$1" in
    -u) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
