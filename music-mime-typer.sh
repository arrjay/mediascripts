#!/bin/bash

set -e

# figure out what MIME type a given file is (file -i), then process it with a file-specific script. expects a single file argument
in=${1}

filetype=$(file -i "${in}"|awk -F': ' '{split($2,s,";");print s[1];}')
case $filetype in
  audio/x-flac)
    # FLAC!
    music-flac-handler.sh
    ;;
  audio/mpeg)
    # this should be mp3
  *)
    echo "I have no idea what type of file this is."
    ;;
esac
