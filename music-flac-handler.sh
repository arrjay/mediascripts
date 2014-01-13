#!/bin/bash

conf=${1}

. "${conf}"

in=${2}

set -e

output_log=$(mktemp ${MUSIC_STAGE}/XXXXXX)
rdid=$(basename ${output_log})

# the tags I am looking for here are modeled after EasyTag.
# required tags
declare -a reqtags=("TITLE" "ARTIST" "ALBUM" "TRACKNUMBER" "DISCNUMBER" "TRACKTOTAL" "DATE")

# counter for missing tags - if this is < 0, we will reject the file
tagmiss=0

# grab comment tags, split on = *but* return single space-separated string
tags=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{ORS=" "} $1 ~ "comment\\[" {split($2,s,"=");print s[1];}')

for tag in ${reqtags[@]} ; do
  if [[ ! $tags == *${tag}* ]] ; then
    echo "$tag missing" >> ${output_log}
    tagmiss=$((${tagmiss} + 1))
  fi
done

# grab picture tag
picturect=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{c=0} $1 ~ "type" {if ($2 ~ "6") {c++;}} END{print c;}')

# generally unused, but the multi-picture code will set it (to 3)
pictureblock=""

case $picturect in
  0)
    # no tags - reject file
    echo "PICTURE block missing" >> ${output_log}
    tagmiss=$((${tagmiss} + 1))
    ;;
  1)
    # one tag - we don't actually care about what *kind* of picture this is
    ;;
  *)
    # more than one tag - *sigh*, find subtype 3 (front cover)
    coverct=$(metaflac --list --block-type=PICTURE "${in}" | awk -F': ' 'BEGIN{c=0} $1 ~ "type" {if ($2 ~ "3"){c++;}} END{print c;}')
    if [[ $coverct -ne 1 ]] ; then
      echo "there is not exactly one front cover picture" >> ${output_log}
      tagmiss=$((${tagmiss} +1))
    else
      # call metaflac again, to get the picture block number
      # this *could* return 0...which is likely insane, but I don't look at it too closely.
      pictureblock=$(metaflac --list --block-type=PICTURE "${in}" | awk -F': ' 'BEGIN{blk=0;sb=0} $0 ~ "METADATA" {split($0,s,"#");sb=s[2];}; $1 ~ "type" {if ($2 ~ "3"){blk=sb;}} END{print blk;}')
    fi
    ;;
esac

# extract the picture and check format with file - support jpeg and png
picturefile=$(mktemp /tmp/picture.XXXXXX)

if [ -z "${pictureblock}" ]; then
  metaflac --export-picture-to=${picturefile} "${in}"
else
  metaflac --block-number=${pictureblock} --export-picture-to=${picturefile} "${in}"
fi

picturetype=$(file -i ${picturefile} | awk -F': ' '{ split($2,s,";"); print s[1]; }')
case ${picturetype} in
  image/jpeg)
    ;;
  image/png)
    ;;
  *)
    echo "I do not understand the covert art image format" >> ${output_log}
    tagmiss=$((${tagmiss} +1))
    ;;
esac

rm "${picturefile}"

# okay, let's start reading the tag content (we actually want this to rename the file to something sane, even if rejected)
# the awk while loops here let us cope with = existing as a tag value
title=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "TITLE" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')
artist=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "ARTIST" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')
album=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "ALBUM" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')
tracktotal=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "TRACKTOTAL" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')
tracknumber=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "TRACKNUMBER" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')
discnumber=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "DISCNUMBER" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')
compilation=$(metaflac --list "${in}" | awk -F': ' 'BEGIN{OFS="=";x=2} $2 ~ "COMPILATION" {e=split($2,s,"="); while(x<=e){print s[x];x++};}')

# set compilation to 0 if we're not set
if [ -z ${compilation} ] ; then
  compilation=0
fi

# check if the discnumber field is formatted like we want
# we read discnumber as a string, delimited as current/total
# we don't do this with bash RE cheats because it can return single-digit entries.
disctotal=$(echo ${discnumber} | awk -F'/' '{ print $2 }')
if [ -z ${disctotal} ] ; then
  echo "There is no total # of discs recorded" >> ${output_log}
  tagmiss=$((${tagmiss} +1))
else
  # get the actual current disc number and make sure it's sane
  cdisc=$(echo ${discnumber} | awk -F'/' '{ print $1 }')
  if [ "${cdisc}" -gt "${disctotal}" ] ; then
    echo "The current disc number is greater than the disc total" >> ${output_log}
    tagmiss=$((${tagmiss} +1))
  fi
fi

# if discnumber and disctotal are set, figure out if we're a multi-disc album.
if [ ! -z ${cdisc} ] && [ ! -z ${disctotal} ] ; then
  if [ ${disctotal} -ne 1 ] ; then
    multidisc=1
  else
    multidisc=0
  fi
elif [ ! -z ${cdisc} ] ; then
  if [ ${cdisc} -gt 1 ] ; then
    # fallback - at least grab if we're on disc 2!
    multidisc=1
  fi
else
  multidisc=0
fi

# function for mangling names in a way I can stand to see them on a filesystem
function fsmangle {
  output=${1//&/n}
  output=${output//!/_}
  # finish with tr to remove any /'s
  output=$(echo ${output} | tr / _)
  echo ${output}
  unset output
}

fs_artist=$(fsmangle "${artist}")
fs_album=$(fsmangle "${album}")
fs_title=$(fsmangle "${title}")

# function to add leading zeroes of appropriate
function lz {
  if [ ! -z "$tracktotal" ]; then
    printf "%0${#tracktotal}d" "${1}"
  else
    # ask paramter 2 what to do, here
    printf "%0${2}d" "${1}"
  fi
}

# tracknumbers are generally two digit padded
fs_tracknumber=$(lz "${tracknumber}" 2)
# discs are generally one digit padded
fs_cdisc=$(lz "${tracknumber}" 1)

# establish a working set name (in case of rejection)
wname=
# if we are a compilation, we get a slightly different naming. things with more than one disc get a slightly different naming.
if [ ${compilation} -ne 1 ]; then
  wname="${fs_artist} - ${fs_album}"
else
  wname="COMPILATION - ${fs_ablum}"
fi

# multi-disc albums get a disc number now
if [ ${multidisc} -eq 1 ] ; then
  wname="${wname} (Disc {$fs_cdisc}) - "
else
  wname="${wname} - "
fi

# track number, title now
wname="${wname} ${fs_tracknumber} - ${fs_title}"

# compilations get the artist name now.
if [ ${compilation} -eq 1 ]; then
  wname="${wname} (${fs_artist})"
fi

# if we have any tag errors at this point, move the file to a rejection point, save the log, and stop.
if [ $tagmiss -ne 0 ] ; then
  mv "${in}" "${MUSIC_STAGE}/${wname}.${rdid}.flac"
  mv "${output_log}" "${MUSIC_STAGE}/${wname}.${rdid}.txt"
  exit 1
fi

# okay, now, check in the tree if we've seen this before
if [ ${compilation} -ne 1 ] ; then
  # the easiest way to do a case insensitive check seems to be find of depth 1 with iname
  artistct=$(find "${MUSIC_ROOT}" -type d -maxdepth 1 -iname "${fs_artist}"| wc -l)
  if [ "${artistct}" -gt 0 ] ; then
    # see if we differ from a destdir by case (which means it doesn't exist)
    if [ ! -d "${MUSIC_ROOT}/${fs_artist}" ] ; then
      echo "case mismatch in artist name tag: value ${fs_artist}" >> ${output_log}
      mv "${in}" "${MUSIC_STAGE}/${wname}.${rdid}.flac"
      mv "${output_log}" "${MUSIC_STAGE}/${wname}.${rdid}.txt"
      exit 1
    fi
  else
    mkdir "${MUSIC_ROOT}/${fs_artist}"
  fi
fi

# dpath is where we hold most of the path
dpath=
# now, check for album directory
if [ ${compilation} -ne 1 ] ; then
  albumct=$(find "${MUSIC_ROOT}/${fs_artist}" -type d -maxdepth 1 -iname "${fs_album}"|wc -l)
  if [ "${albumct}" -gt 0 ] ; then
    if [ ! -d "${MUSIC_ROOT}/${fs_artist}/${fs_album}" ] ; then
      echo "case mismacth in album name tag: value ${fs_album}" >> ${output_log}
      mv "${in}" "${MUSIC_STAGE}/${wname}.${rdid}.flac"
      mv "${output_log}" "${MUSIC_STAGE}/${wname}.${rdid}.txt"
      exit 1
    else
      dpath="${MUSIC_ROOT}/${fs_artist}/${fs_album}"
    fi
  else
    mkdir "${MUSIC_ROOT}/${fs_artist}/${fs_album}"
    dpath="${MUSIC_ROOT}/${fs_artist}/${fs_album}"
  fi
else
  albumct=$(find "${MUSIC_ROOT}/${COMP_DIR}" -type d -maxdepth 1 -iname "${fs_album}"|wc -l)
  if [ "${albumct}" -gt 0 ] ; then
    if [ ! -d  "${MUSIC_ROOT}/${COMP_DIR}/${fs_album}" ] ; then
      echo "case mismacth in album name tag: value ${fs_album}" >> ${output_log}
      mv "${in}" "${MUSIC_STAGE}/${wname}.${rdid}.flac"
      mv "${output_log}" "${MUSIC_STAGE}/${wname}.${rdid}.txt"
      exit 1
    else
      dpath="${MUSIC_ROOT}/${COMP_DIR}/${fs_album}"
    fi
  else
    mkdir "${MUSIC_ROOT}/${COMP_DIR}/${fs_album}"
    dpath="${MUSIC_ROOT}/${COMP_DIR}/${fs_album}"
  fi
fi

# if we are a multi-disc set, create and add the disc path now
if [ ${multidisc} -eq 1 ] ; then
  mkdir "${dpath}/Disc ${fs_cdisc}"
  dpath="${dpath}/Disc ${fs_cdisc}"
fi

# we actually should know everything there is to know concerning the file destination. see if it exists now.
if [ ${compilation} -ne 1 ] ; then
  if [ -f "${dpath}/${fs_tracknumber} - ${fs_title}.flac" ] ; then
    echo "file already exists: ${dpath}/${fs_tracknumber} - ${fs_title}.flac" >> ${output_log}
    mv "${in}" "${MUSIC_STAGE}/${wname}.${rdid}.flac"
    mv "${output_log}" "${MUSIC_STAGE}/${wname}.${rdid}.txt"
    exit 1
  else
    mv "${in}" "${dpath}/${fs_tracknumber} - ${fs_title}.flac"
  fi
else
  if [ -f "${dpath}/${fs_tracknumber} - ${fs_title} \(${fs_artist}\).flac" ] ; then
    echo "file already exists: ${dpath}/${fs_tracknumber} - ${fs_title} \(${fs_artist}\).flac" >> ${output_log}
    mv "${in}" "${MUSIC_STAGE}/${wname}.${rdid}.flac"
    mv "${output_log}" "${MUSIC_STAGE}/${wname}.${rdid}.txt"
    exit 1
  else
    mv "${in}" "${dpath}/${fs_tracknumber} - ${fs_title} \(${fs_artist}\).flac"
  fi
fi
