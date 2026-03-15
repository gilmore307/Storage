# TUN Rule-Mode Proxy Keywords

## Purpose
This file is the human-editable source of truth for the current **keyword-based proxy rules** used by the first-pass TUN rule-mode configs.

Current intent:
- domestic sites should prefer `direct`
- selected overseas / blocked / developer services should prefer `proxy`
- private/LAN traffic should stay `direct`

## Current proxy keywords
- `google`
- `youtube`
- `openai`
- `anthropic`
- `github`

## How to extend
When you find a site or service that should consistently go through the proxy, add one keyword per bullet here.

Examples:
- `x`
- `twitter`
- `telegram`
- `discord`
- `notion`
- `claude`

## Practical rule of thumb
Prefer keywords only when they are stable and obvious.

Good candidates:
- service/product names
- main domain identity words
- tooling/vendor names that are unlikely to collide with domestic sites

Avoid:
- very short generic words
- words likely to appear on unrelated Chinese sites
- huge mixed lists without testing

## Important note
This file is documentation / operator source-of-truth.
The current sing-box JSON configs still contain their own inline rule arrays, so config files must be updated after editing this file.

Current files that should stay aligned:
- `projects/Storage/network-framework/node1/config-tun-rule.json`
- `projects/Storage/network-framework/node2/config-tun-rule.json`
- `node/config/singbox-client-tun-rule-template.json`

## Next possible improvement
If this keyword list grows, convert it into a machine-readable source and generate the JSON configs from it instead of editing all copies by hand.
