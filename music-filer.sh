#!/bin/bash

## script runs periodically and picks up files from drop directory.
##  assumes samba, for checking file locks.

# safety locks on
set -e

home=${1}

cd ${home}

# source config pieces
. ${home}/music.conf

# Store files as an array, to cope with spaces. Store locks as a chunk of text, we just need to search for any given file *inside* it.
# pray to god you don't encounter a file name with a newline in it.

# IFS abuse - can you make this work an actual print0 find?
oifs=${IFS}
IFS=$'\n'
# first get files, then get locks.
files=($(find ${MUSIC_UPLOAD}/ -type f))
# awkwarrrd (and brittle, we print any fields from $8 to NF-5, hoping the last 5 are the date)
locks=$(smbstatus -Lb | awk "BEGIN {ORS=\" \"} \$7 ~ \"^${MUSIC_UPLOAD}\" {i=8;e=(NF - 5);while(i<=e){printf \"%s \",\$i;i++}printf \" \" }")

# if file is not locked, move to stage directory and set ownership
for file in ${files[@]}; do
  # safeties off
  set +e
  # check for lock, 0 means we found one
  echo ${locks}|grep -q ${file}
  if [ $? -ne 0 ] ; then
    # re-enable
    set -e

    # get a new file name set up, move it
    newfile=$(mktemp ${MUSIC_STAGE}/file.XXXXXXXX)
    mv "${file}" "${newfile}"

    fext=${file#*.} # what someone named a file to, at least
    # if we have a file extension, move the file *again*, to have the extension.
    if [ ! -z "${fext}" ] ; then
      mv "${newfile}" "${newfile}.${fext}"
      newfile="${newfile}.${fext}"
    fi

    # set perms to something sane, call the next script as _music
    chown ${MUSIC_USER}:${MUSIC_GROUP} "${newfile}"
    chmod 0600 "${newfile}"
    sudo -u ${MUSIC_USER} ${MUSIC_STAGE2_SCRIPT} "${1}" "${newfile}"
  fi
  # turn this back on, in case there was a lock
  set -e
done

# we can stop the IFS abuse now...
IFS=${oifs}
