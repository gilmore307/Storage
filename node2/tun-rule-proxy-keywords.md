# TUN Rule-Mode Proxy Keywords

这是 **唯一的关键词配置入口**。

- 文件位置现在在 `node1/tun-rule-proxy-keywords.md`
- `VPN AUTO` 会先按中国/局域网规则直连，其他流量默认走 VPN
- 这里的关键词用于 **强制代理覆盖**，适合补充 Google / OpenAI / GitHub 之类需要稳定走 VPN 的站点
- `VPN ON` 不看关键词，直接让全部流量走代理
- 修改这个文件后，在托盘菜单点击 `Reload` 就会重新加载并生效
- 也可以直接用托盘菜单里的 `Add Keyword` 快捷追加，保存后会自动 `Reload`

## Current proxy keywords
- `google`
- `youtube`
- `openai`
- `anthropic`
- `github`
- `discord`
- `chatgpt`
- `x`
- `firstrade`
- `steampowered`
- `docker`
- `openclaw`

## How to extend
一行一个关键词，继续按 bullet 形式追加就行。

## Rule of thumb
优先写稳定、辨识度高、不会误伤国内站点的关键词。

适合：
- 服务名
- 产品名
- 主域名识别词
- 明确的厂商名

避免：
- 太短的通用词
- 容易和无关网站撞上的词
- 一次性堆很多没验证过的词
