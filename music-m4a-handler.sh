#!/bin/bash

home=${1}

. "${home}"/music.conf

in=${2}

set -e

output_log=$(mktemp ${MUSIC_STAGE}/XXXXXX)
rdid=$(basename ${output_log})

# okay, let's find out a little more specifically what kind of mp4 this is.
# uses ffmpeg2 and an awk state machine.
ffmpeg_out=$(mktemp /tmp/XXXXXX)
# ffmpeg will always bitch here
set +e
ffmpeg -i "${in}" 2> "${ffmpeg_out}" 
set -e

streams=$(cat "${ffmpeg_out}" | awk 'BEGIN{scount=0} $1 ~ "Stream" {scount++;} END{print scount;}')
# the rest of these tests only make sense if there is one stream...I think.
styp=$(cat "${ffmpeg_out}" | awk -F": " '$2 ~ "Audio" { split($3,s,","); print s[1]; }')
title=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "title" { print $2 }')
artist=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "artist" { print $2 }')
composer=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "composer" { print $2 }')
album=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "album" { print $2 }')
genre=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "genre" { print $2 }')
trackno=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "track" { print $2 }')
discno=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "disc" { print $2 }')
year=$(cat "${ffmpeg_out}" | awk -F": " '$1 ~ "date" { print $2 }')

if [ $streams -ne 1 ] ; then
  echo "there is not exactly one stream here. did you cross the streams?" >> ${output_log}
  mv "${in}" "${MUSIC_STAGE}/${rdid}.m4a"
  mv "${output_log}" "${MUSIC_STAGE}/${rdid}.txt"
  exit 1
fi

case ${styp} in
  # alac - upgrade to flac, then make it the flac script's problem.
  alac)
    # convert
    ffmpeg -i "${in}" "${MUSIC_STAGE}/${rdid}.flac" 2> /dev/null
    # copy tags
    metaflac "--set-tag=TITLE=${title}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=ARTIST=${artist}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=COMPOSER=${composer}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=ALBUM=${album}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=GENRE=${genre}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=TRACKNUMBER=${trackno}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=DISCNUMBER=${discno}" "${MUSIC_STAGE}/${rdid}.flac"
    metaflac "--set-tag=DATE=${year}" "${MUSIC_STAGE}/${rdid}.flac"
    # remove the old alac file
    rm "${in}"
    # care not about what music-flac-handler has to say
    set +e
    ${home}/bin/music-flac-handler.sh "${home}" "${MUSIC_STAGE}/${rdid}.flac"
    set -e
    ;;
  *)
    echo "I do not understand substream type ${styp}" >> "${output_log}"
    mv "${in}" "${MUSIC_STAGE}/${rdid}.m4a"
    mv "${output_log}" "${MUSIC_STAGE}/${rdid}.txt"
    ;;
esac

rm "${output_log}"
