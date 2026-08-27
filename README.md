# 日顺智能 (Rishun) 自定义集成

将日顺智能（Rishun）的智能设备接入 Home Assistant。

## 功能特点

- 支持设备类型：
  - 灯光（开关/调光）
  - 开关（面板）
  - 窗帘（电动）
  - 空调、地暖、新风
  - 空气质量传感器（温湿度、PM2.5、CO2、CH2O、TVOC）
- 通过云 API 轮询状态（可配置更新间隔）
- 操作后立即更新本地状态，保证响应速度

## 安装方法

### 通过 HACS（推荐）
1. 在 HACS 中添加自定义仓库：
   - 点击 HACS → 集成 → 右上角菜单 → 自定义仓库
   - 输入你的 GitHub 仓库地址（例如 `https://github.com/quanxiumei-maker/rishun-ha`）
   - 类别选择“集成”
2. 点击“安装”即可。

### 手动安装
1. 下载本仓库的 `custom_components/rishun/` 文件夹。
2. 将其复制到 Home Assistant 的 `custom_components/` 目录下。
3. 重启 Home Assistant。

## 配置

1. 进入 Home Assistant → 配置 → 设备与服务 → 添加集成 → 搜索“日顺智能”。
2. 输入你的日顺智能账号（手机号）和密码。
3. 如果存在多个房屋，会弹出选择房屋列表。
4. 完成配置后，设备会自动出现。
