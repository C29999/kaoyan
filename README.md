# 春雪考研助手 (Spring Snow Kaoyan)

> 一站式考研复习桌面应用 · 风格仿 VSCode / TraeCode

一款基于 **PyQt5** 的考研学习桌面软件，集错题本、单词背诵、阅读理解、翻译/写作/口语练习、专注计时、PDF 阅读、AI 助手（硅基流动 / 智谱 AI）于一体。整体 UI 风格参考 VSCode / TraeCode，支持浅色 / 深色（牛奶色）主题动态切换，切换时带丝滑渐变过渡。

---

## 特性一览

| 模块 | 功能 |
|------|------|
| **🏠 主页 Dashboard** | 每日励志语录（5 秒自动轮播 + 淡入淡出）、考研倒计时、近期目标、今日任务 |
| **📖 英语错题本** | 图片上传 + 缩略图、答案/解析编辑、模糊搜索、按日期/次数排序、双击查看大图、批量删除 |
| **📚 单词背诵 / 阅读 / 翻译 / 写作 / 口语** | 五大英语训练 Tab（占位模块，后续扩展） |
| **🧮 数学 / 🎓 专业课 / 🏫 择校 / 🎬 网课学习** | 学习辅助模块（部分占位） |
| **📄 PDF 阅读** | 内置 PDF 阅读 + 注释（占位） |
| **🍅 专注模式** | 番茄钟计时器，仿极简现代风 |
| **🤖 AI 助手** | 内置右侧栏，支持硅基流动 / 智谱 AI 双平台、流式响应、模型下拉切换、Key 配置对话框 |
| **🎨 主题切换** | 浅色 / 深色（牛奶色）双主题 + iOS 风格长圆形滑动开关 + 800ms 丝滑渐变动画 |
| **🌐 联网浏览器** | 内置 QtWebEngine，可直接看网课视频 |

---

## ⚡ 三步在新电脑跑起来

### Windows

```powershell
# 1. 克隆仓库
git clone git@github.com:C29999/kaoyan.git
cd kaoyan

# 2. 安装依赖 (首次运行)
pip install -r requirements.txt

# 3. 启动程序
python spring_snow_pyqt.py
```

或者直接 **双击 `launch_with_console.bat`**，脚本会自动检测 Python 并安装依赖。

### macOS / Linux

```bash
git clone git@github.com:C29999/kaoyan.git
cd kaoyan
pip3 install -r requirements.txt
python3 spring_snow_pyqt.py
```

> ⚠️ SSH 推送需要先在 GitHub 添加本机的 SSH 公钥 (`https://github.com/settings/keys`)。
> 如果还没配 SSH，也可以用 HTTPS：
> ```bash
> git clone https://github.com/C29999/kaoyan.git
> ```

---

## 系统要求

- **Python 3.8+**（推荐 3.10+）
- **Windows 10/11** / macOS 11+ / Ubuntu 20.04+
- 约 **300MB** 磁盘空间（PyQt5 + PyQtWebEngine）
- 联网（AI 功能和网课学习需要）

---

## 目录结构

```
kaoyan/
├── spring_snow_pyqt.py      # 主程序（约 8800 行单文件）
├── requirements.txt          # 依赖清单
├── launch_with_console.bat   # Windows 一键启动脚本
├── .gitignore                # Git 忽略规则
├── README.md                 # 本文件
├── image/                    # 错题图片（不上传，含 Edge 浏览器 profile）
├── kaoyan_data.json          # 用户数据：设置/任务/目标（不上传）
├── kaoyan_english_data.json  # 错题本数据（不上传）
├── ai_chat_history.json      # AI 对话历史（不上传）
└── focus_sessions.json       # 专注记录（不上传）
```

> 💡 用户数据全部存为 JSON 格式，删了不影响程序使用。

---

## 🎨 主题切换

标题栏右上角有 **☀️ / 🌙 长圆形开关**，一键切换：

- **浅色模式**：白底 + 浅灰边 + 蓝色强调
- **深色模式**：深蓝底 + 牛奶色文字（`#f5f0e1`）+ 暖琥珀强调色

切换时有 **800ms 丝滑渐变**：界面渐变到目标色 → 内部样式切换 → 渐变回显示状态。

> 完整弹窗：点开关旁的 🎨 按钮，可预览两种主题并直接选择。

---

## 🤖 AI 助手配置

1. 程序右栏点击 **🔑 Key** 按钮（或在 AI 面板右上角配置）
2. 选择提供商（**硅基流动** / **智谱 AI** / **自定义**）
3. 填入 API Key
4. 选择模型
5. 点 **测试连接** → **保存**

支持的模型（默认）：

| 平台 | 模型 |
|------|------|
| 硅基流动 | Qwen/Qwen2.5-7B-Instruct, deepseek-ai/DeepSeek-V2.5, Pro/Qwen/Qwen2-7B-Instruct |
| 智谱 AI | glm-4-flash, glm-4-air, glm-4-plus |
| 自定义 | 任意 OpenAI 兼容 API |

> Key 保存在本地 `kaoyan_data.json`，不会上传任何地方。

---

## ❓ 常见问题

**Q: 启动报错 `ModuleNotFoundError: No module named 'PyQt5'`?**
A: 重新执行 `pip install -r requirements.txt`

**Q: 主题切换时没有动画?**
A: 800ms 渐变很丝滑，如果你看到的是瞬间切换，请更新代码 `git pull`

**Q: AI 一直显示「AI 正在思考」?**
A: 检查网络 + Key 是否正确，在 🔑 弹窗里点「测试连接」

**Q: 网课视频打不开?**
A: 需要联网；首次启动 QtWebEngine 会有几个 cache 警告，不影响使用

**Q: 想清空所有数据重新开始?**
A: 删除 `kaoyan_*.json` `ai_chat_history.json` `focus_sessions.json` 即可

---

## 🛠 技术栈

- **Python 3.8+** + **PyQt5 5.15+**
- **PyQtWebEngine**（网课学习 + 浏览器）
- **requests**（AI API 调用）
- **QSS**（样式表，仿 VSCode / TraeCode）
- **QPropertyAnimation** + **QGraphicsOpacityEffect**（丝滑动画）
- 单文件架构（`spring_snow_pyqt.py` ~8800 行）

---

## 📜 许可证

仅供个人学习使用。

---

## 🙏 致谢

- UI 设计灵感来自 [VSCode](https://code.visualstudio.com/) 和 Trae IDE
- AI 模型由 [硅基流动](https://siliconflow.cn/) 和 [智谱 AI](https://www.zhipuai.cn/) 提供
