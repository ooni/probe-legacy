#!/bin/bash
set -e

DST_DIR="whatsapp_inputs/"

# Known Whatsapp web URLs
WHATSAPP_URLS="
www.whatsapp.com
web.whatsapp.com
www.whatsapp.com/cidr.txt
whatsapp.com
sro.whatsapp.net/client/iphone/iq.php
sro.whatsapp.net/client/android/iq.php
static.reverse.softlayer.com
"

WHATSAPP_DOMAINS="
www.whatsapp.com
web.whatsapp.com
whatsapp.com
sro.whatsapp.net
static.reverse.softlayer.com
"

URL_LIST=$(mktemp)
DOMAIN_LIST=$(mktemp)

for URL in ${WHATSAPP_URLS}; do
    echo -e "http://${URL}\nhttps://${URL}" >> ${URL_LIST}
done

for DOMAIN in ${WHATSAPP_DOMAINS}; do
    echo ${DOMAIN} >> ${DOMAIN_LIST}
done

DOMAIN_HASH=$(shasum -a 256 ${DOMAIN_LIST} | cut -d ' ' -f1)
URL_HASH=$(shasum -a 256 ${URL_LIST} | cut -d ' ' -f1)

mv $URL_LIST $DST_DIR/$URL_HASH
echo "{id: ${URL_HASH}, name: URLs for whatsapp, description: 'The URLs used by whatsapp', version: 1, author: ooni, date: 2016-05-05T180000Z}" > "$DST_DIR/$URL_HASH.desc"
mv $DOMAIN_LIST $DST_DIR/$DOMAIN_HASH
echo "{id: ${DOMAIN_HASH}, name: Domains for whatsapp, description: 'The domains used by whatsapp', version: 1, author: ooni, date: 2016-05-05T180000Z}" > "$DST_DIR/$DOMAIN_HASH.desc"
