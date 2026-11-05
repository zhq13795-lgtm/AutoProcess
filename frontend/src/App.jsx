import { useState } from 'react';

const outputHeaders = {
  sales: ['SKU', 'Quantity', 'Unit Price', 'Amount'],
  inventory: ['SKU', 'Quantity'],
};

export default function App() {
  const [region, setRegion] = useState('EU');
  const [file, setFile] = useState(null);
  const [inspection, setInspection] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(endpoint) {
    if (!file) {
      setError('请先选择 .xlsx 文件。');
      return;
    }
    setBusy(true);
    setError('');
    if (endpoint === 'process') setResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('region', region);
      const response = await fetch(`/api/${endpoint}`, { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '处理失败');
      if (endpoint === 'inspect') setInspection(data);
      else setResult(data);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <header>
        <div className="eyebrow">EXCEL WORKFLOW</div>
        <h1>AutoProcess</h1>
        <p>检查代理商报表字段，应用区域规则，导出标准化销售与库存数据。</p>
      </header>

      <section className="panel controls">
        <div className="control">
          <label htmlFor="region">业务区域</label>
          <select id="region" value={region} onChange={(event) => { setRegion(event.target.value); setInspection(null); setResult(null); }}>
            <option value="EU">欧洲 EU</option>
            <option value="NA">北美 NA</option>
            <option value="APAC">亚太 APAC</option>
          </select>
        </div>
        <div className="control file-control">
          <label htmlFor="file">原始报表</label>
          <input id="file" type="file" accept=".xlsx" onChange={(event) => { setFile(event.target.files?.[0] || null); setInspection(null); setResult(null); }} />
        </div>
        <div className="actions">
          <button className="secondary" disabled={busy} onClick={() => submit('inspect')}>检查字段</button>
          <button disabled={busy} onClick={() => submit('process')}>{busy ? '处理中…' : '清洗报表'}</button>
        </div>
        <a className="sample" href={`/api/sample?region=${region}`}>下载 {region} 示例报表</a>
        {error && <div role="alert" className="error">{error}</div>}
      </section>

      {inspection && (
        <section className="panel">
          <div className="section-title"><h2>字段检查</h2><span>{inspection.sheets.length} 个工作表</span></div>
          <div className="cards">
            {inspection.sheets.map((sheet) => (
              <article className="card" key={sheet.name}>
                <h3>{sheet.name}</h3>
                <p>{sheet.kind || '未识别'} · {sheet.rows} 行</p>
                <dl>{Object.entries(sheet.mapping).map(([field, column]) => <div key={field}><dt>{field}</dt><dd>{sheet.headers[column]}</dd></div>)}</dl>
              </article>
            ))}
          </div>
        </section>
      )}

      {result && (
        <section className="panel">
          <div className="section-title">
            <div><h2>处理结果</h2><span>{result.region} · {result.sheets.length} 个工作表</span></div>
            <a className="download" href={`/api/download/${result.run_id}`}>下载标准 Excel</a>
          </div>
          {result.ignored_sheets.length > 0 && <p className="muted">未处理：{result.ignored_sheets.join('、')}</p>}
          {result.sheets.map((sheet) => (
            <article className="result" key={sheet.source_sheet}>
              <div className="result-heading"><h3>{sheet.source_sheet}</h3><span>{sheet.rows_in} 行输入 → {sheet.rows_out} 行输出</span></div>
              <p className="muted">规则 {sheet.recipe_id} · {sheet.reused ? '复用已识别字段' : '新识别字段'}</p>
              <div className="trace">{sheet.trace.map((step) => <div key={step.step}><b>{step.step}</b><span className={step.status}>{step.status}</span><small>{step.detail}</small></div>)}</div>
              <div className="table-scroll"><table><thead><tr>{outputHeaders[sheet.kind].map((name) => <th key={name}>{name}</th>)}</tr></thead><tbody>{sheet.preview.map((row, index) => <tr key={index}>{row.map((value, column) => <td key={column}>{value}</td>)}</tr>)}</tbody></table></div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
