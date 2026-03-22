# OpenClaw tray app

## 直接运行源码（不打包 exe）

### 1) 安装依赖

```powershell
python -m pip install -r requirements-tray.txt
```

### 2) 启动

最简单：

```powershell
python .\openclaw_node_tray_app.py
```

指定 profile：

```powershell
python .\openclaw_node_tray_app.py --profile .\node-1-office.profile.json
```

调试时保留控制台：

```powershell
python .\openclaw_node_tray_app.py --console
```

## 当前托盘菜单

菜单现在是平铺展开的：

- `Node ON`
- `Node OFF`
- 分割线
- `VPN ON`
- `VPN AUTO`
- `VPN OFF`
- `Reload`
- `Exit`

其中：

- `VPN ON`：全部流量走 VPN
- `VPN AUTO`：中国/局域网流量优先直连，其余默认走 VPN；关键词可做强制代理覆盖
- `VPN OFF`：关闭 VPN
- `Reload`：只重载 VPN 配置与关键词，不重启整个托盘程序

## 关键词配置入口

关键词现在只从 `node1/tun-rule-proxy-keywords.md` 读取。

- `node-1-office.profile.json` 不再保存关键词列表
- `resources/config-tun-rule.template.json` 也不再保存实际关键词内容
- 修改关键词后，点击托盘菜单里的 `Reload` 即可生效
- 旧的 `resources/tun-rule-proxy-keywords.md` 可以删除

## AUTO 模式现在怎么分流

- 局域网 / 私网：直连
- 中国站点：直连
- 关键词命中的站点：强制走 VPN
- 其他流量：默认走 VPN

这比“只按关键词分流”更接近日常使用场景，比如 Google 走 VPN、哔哩哔哩直连。

## 源码直启版做了什么

- 默认优先读取同目录下的 `node-1-office.profile.json`
- 继续兼容 `--profile`、环境变量和原来的 exe/profile 命名方式
- Windows 下会优先尝试切到 `pythonw.exe` 后台启动，避免常驻控制台
- Windows 下默认会尝试请求管理员权限，以兼容 VPN/TUN 场景
- 可用 `--no-pythonw` / `--no-admin` 关闭上述行为

## 保留 exe 打包

```powershell
.\build.ps1
```

构建产物仍然在 `dist\` 目录。
