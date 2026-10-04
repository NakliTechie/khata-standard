#!/bin/bash
B=https://taxinformation.cbic.gov.in
TOK=$(curl -s -X POST -H "Content-Type: application/json" -d '{}' $B/api/authenticate-token | python3 -c 'import sys,json;print(json.load(sys.stdin)["id_token"])')
H1="Authorization1: homeToken $TOK"
list(){ curl -s -H "$H1" -H "language: en" "$B/api/cbic-notification-msts/fetchNotificationByYearAndCategory?page=0&size=100&year=$1&category=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$2")&taxId=1000001"; }
dl(){ curl -s -H "$H1" -H "language: en" "$B/api/cbic-notification-msts/download/$1/ENG" | python3 -c 'import sys,json,base64;open(sys.argv[1],"wb").write(base64.b64decode(json.load(sys.stdin)["data"]))' "$2"; }
"$@"
