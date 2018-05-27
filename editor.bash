#!/usr/bin/env bash
json=
cd /usr/local/share/fonts/ || exit 1
select font in *
	do read -r -p'Text? ' text
		json+="$(
			jq -r -n -c --arg font "$font" --arg text "$text" '.|{"font":$font,"msg":$text}'
		)"$'\n'
	done
	msg="$(
		jq -s '{"cmd":"message","value":.}' <<<"$json"
	)"
	curl -H "X-AIO-Key: $AIO_KEY" \
	     -H 'Content-Type: application/json' \
	     -X POST https://io.adafruit.com/api/feeds/GreenhouseCmds/data.json -d@- < <(
		jq -r -c -n --arg cmd "$msg" '$cmd|{"value":.}'
	)
	echo
