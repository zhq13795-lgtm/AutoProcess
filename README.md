# AutoProcess

面向销售与库存 Excel 报表的轻量处理工具。上传工作簿后可查看字段识别结果，按区域规则清洗数据，并下载统一格式的 Excel 文件。

支持 EU、NA、APAC 三组通用字段别名；销售表输出 SKU、数量、单价和金额，库存表输出 SKU 和数量。处理流程由 LangGraph 编排为检查、规则匹配、执行、校验四步，页面展示每一步的状态。相同区域和表头的字段映射在当前服务进程内复用。

仓库内置的工作簿由程序生成，使用 `SAMPLE-*` 虚构商品编号。处理过程不需要外部模型服务或 API Key。

## 启动

需要 Python 3.11+ 和 Node.js 20+。打开两个终端：

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。先下载页面提供的示例报表，再上传检查字段和清洗。后端接口文档在 `http://127.0.0.1:8000/docs`。

运行后端测试：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests
```

## 当前范围

- 接收 `.xlsx` 文件，单文件不超过 2 MB。
- 识别 Sales / Inventory 工作表；未识别的工作表会被跳过。
- 对缺失的必要字段返回明确错误；无效数据行不进入输出。
- 处理结果和字段映射保存在当前服务进程内，重启后清空。
- 不包含账号体系、第三方消息集成和外部模型调用。
