import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

let input = "";
for await (const part of process.stdin) input += part;
const payload = JSON.parse(input);
const output = path.resolve(process.argv[2]);
const fields = ["邮箱账号", "邮箱密码", "Agnes密码", "API Key", "状态", "说明"];
const headers = ["邮箱账号", "邮箱密码", "Agnes 登录密码", "API Key", "状态", "说明"];
if (payload.proxy_test) {
  fields.push("注册出口IP", "取钥出口IP", "密钥认证", "用户ID");
  headers.push("注册出口 IP", "取钥出口 IP", "密钥认证", "用户 ID");
}
const lastColumn = String.fromCharCode(64 + fields.length);
const literal = value => typeof value === "string" && /^[\s]*[=+@-]/.test(value)
  ? "'" + value : value ?? "";
const workbook = Workbook.create();
const sheets = [];
const summarySheets = [];

if (payload.proxy_test) {
  const report = payload.proxy_test;
  const sheet = workbook.worksheets.add("IP实测与分配");
  sheet.showGridLines = false;
  sheet.tabColor = "#253858";
  sheet.getRange("A1:I38").format = {
    font: { name: "Arial", size: 10, color: "#202B3C" },
    verticalAlignment: "center", rowHeight: 28,
  };
  for (const [column, width] of Object.entries({ A: 34, B: 23, C: 23, D: 19, E: 19, F: 20, G: 20, H: 22, I: 36 })) {
    sheet.getRange(`${column}1:${column}38`).format.columnWidth = width;
  }
  sheet.getRange("A2").values = [["Agnes · 代理实测与分配"]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#253858" };
  sheet.getRange("A2:I2").format.borders = { bottom: { style: "thin", color: "#A6B1C2" } };
  const clean = report.groups.filter(group => group.status === "PASSED");
  const quota = report.recommended_accounts_per_ip ?? (clean.length ? Math.min(...clean.map(group => group.successful_verified_accounts)) : null);
  const completed = payload.rows.filter(row => row["密钥认证"] === "HTTP 200").length;
  sheet.getRange("A4:B12").values = [
    ["每 IP 建议分配账号数", quota ?? "待确定"],
    ["本次已取钥并通过认证", completed],
    ["邮箱清单总数", report.source_mailbox_count],
    ["剩余未完成数", null],
    ["剩余分组数（每组不超配额）", null],
    ["实测并发", report.concurrency],
    ["本轮设置注册提交数／分钟", report.max_registration_submissions_per_minute],
    ["测试前记录流量（GB）", report.starting_balance_gb ?? "未提供"],
    ["已记录代理传输（MB）", report.groups.reduce((sum, group) => sum + (group.proxy_sent_bytes || 0) + (group.proxy_received_bytes || 0), 0) / 1e6],
  ];
  sheet.getRange("B7").formulas = [["=B6-B5"]];
  sheet.getRange("B8").formulas = [['=IF(ISNUMBER(B4),ROUNDUP(B7/B4,0),"待确定")']];
  sheet.getRange("B4:B11").setNumberFormat("#,##0");
  sheet.getRange("B12").setNumberFormat("0.00");
  sheet.getRange("A4:B4").format.font.bold = true;
  sheet.getRange("D4").values = [[report.ip_limit_observed ? "实测：当前 IP 触发平台限流，请查看请求账本" : quota ? "配额依据：通过的固定出口小批次" : "尚未得到完整固定出口小批次"]];
  sheet.getRange("D5").values = [["实测成功数能证明下限，不能证明平台最高上限。"]];
  sheet.getRange("D9").values = [["已记录值含排错，部分中断流量未累计；供应商账单未读取。"]];
  sheet.getRange("D11").values = [["截图余额为测试前记录，未读取测试后的后台余额。"]];
  sheet.getRange("D10").values = [["程序测试设置，非平台公布的速度上限。"]];
  sheet.getRange("D4:I11").format.wrapText = false;
  const successfulTraffic = report.groups.flatMap(group => group.accounts).filter(account => account.accepted_sample);
  const averageMb = successfulTraffic.reduce((sum, account) => sum + account.proxy_sent_bytes + account.proxy_received_bytes, 0) / successfulTraffic.length / 1e6;
  sheet.getRange("A13:B14").values = [
    ["优化前完整流程样本（MB／账号）", Number.isFinite(averageMb) ? averageMb : null],
    ["优化前流程全量粗估（GB）", null],
  ];
  sheet.getRange("B14").formulas = [["=B6*B13/1000"]];
  sheet.getRange("B13:B14").setNumberFormat("0.00");
  sheet.getRange("D13").values = [[`${successfulTraffic.length} 个完整样本；含网页资源和验证请求，非供应商扣费值。`]];
  sheet.getRange("D14").values = [["旧流程估算，不作为优化后的采购依据；优化后完整开户待实测。"]];
  const groupRows = report.groups.map(group => {
    const submitted = group.accounts.filter(account => [account, ...(account.previous_attempts || [])].some(attempt => (attempt.checkpoints || []).some(point => point.phase === "REGISTRATION_SUBMITTED"))).length;
    const status = group.status === "IP_LIMIT_OBSERVED" ? "本组触发平台 IP 限流"
      : group.status === "PASSED" ? "该固定出口小批次通过"
      : group.status === "RETIRED_AFTER_EGRESS_CHANGE" ? "已换 IP，单独核查取钥"
      : group.error_code || "本组未完成";
    return [group.group, group.original_egress_ip || group.egress_ip || "", group.mixed_egress ? group.egress_ip || "" : "同注册出口", submitted,
      group.accounts.filter(account => account.key_authenticated).length, group.successful_verified_accounts || 0,
      ((group.proxy_sent_bytes || 0) + (group.proxy_received_bytes || 0)) / 1e6,
      group.session_minutes || "未验证", status];
  });
  sheet.getRange("A16:I16").values = [["组别", "注册出口 IP", "取钥出口 IP", "已提交注册数", "认证通过的 Key", "全程同 IP 完成数", "传输合计（MB）", "设定时效（分钟）", "本组结果"]];
  const groupLastRow = 16 + groupRows.length;
  sheet.getRange(`A17:I${groupLastRow}`).values = groupRows;
  sheet.getRange(`A17:A${groupLastRow}`).setNumberFormat("0");
  sheet.getRange(`D17:F${groupLastRow}`).setNumberFormat("0");
  sheet.getRange(`G17:G${groupLastRow}`).setNumberFormat("0.00");
  sheet.tables.add(`A16:I${groupLastRow}`, true, "AgnesProxyObservations").showFilterButton = true;
  sheet.getRange("A16:I16").format = {
    fill: "#253858", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 36, wrapText: true,
    borders: { insideVertical: { style: "thin", color: "#FFFFFF" } },
  };
  sheet.getRange(`A17:I${groupLastRow}`).format.rowHeight = 36;
  sheet.getRange(`I17:I${groupLastRow}`).format.wrapText = true;
  sheet.getRange("A22").values = [["批量执行规则"]];
  sheet.getRange("A22").format.font.bold = true;
  const notes = [
    quota ? `首批每个实际出口安排 ${quota} 个账号；记录实际 IP，按平台规则决定后续批次。` : "先完成固定出口小批次，再确定每 IP 分配数。",
    "同批开始、每个账号和批末核验出口；发现换 IP，暂停新注册并保留已提交记录。",
    report.ip_limit_observed ? "本批已因平台 IP 限流暂停；限流窗口需按平台实际响应核查。" : "本次结果仅对应已授权的样本测试，不代表其他批次结果。",
    "来源：本次显式提供的授权账号清单、代理报告与本机实测记录。",
  ];
  sheet.getRange("A23:A26").values = notes.map(value => [value]);
  if (report.ip_limit_observed) sheet.getRange("A27").values = [["实际响应：HTTP 400 /api/verification — Too many registration attempts from this IP. Please try again later"]];
  if (report.download_optimization) {
    const test = report.download_optimization;
    sheet.getRange("A30").values = [["网页加载优化实测 · 已有账号检查"]];
    sheet.getRange("A30").format.font.bold = true;
    sheet.getRange("A31:D31").values = [["指标", "优化前", "优化后首次", "缓存后的下一次"]];
    sheet.getRange("A31:D31").format = { fill: "#253858", font: { bold: true, color: "#FFFFFF" }, rowHeight: 30 };
    sheet.getRange("A32:D33").values = [
      ["代理传输（MB）", test.baseline_bytes / 1e6, test.cold_bytes / 1e6, test.warm_bytes / 1e6],
      ["流程耗时（秒）", test.baseline_seconds, test.cold_seconds, test.warm_seconds],
    ];
    sheet.getRange("B32:D33").setNumberFormat("0.00");
    sheet.getRange("A35").values = [["对照范围：读取注册表单、登录已有账号、核对身份及已有密钥列表；新增注册与密钥均为 0。"]];
    sheet.getRange("A36").values = [["只缓存平台允许公开缓存的网页文件，过滤统计与广告请求；账号登录资料分别保存。"]];
    sheet.getRange("A37").values = [["验证码、新注册及密钥创建未包含在优化对照内，不能据此保证完整开户速度或总流量。"]];
  }
  summarySheets.push({ sheet, range: report.download_optimization ? "A1:I37" : "A1:I27" });
}

function addSheet(name, rows, tableName) {
  const values = rows.map(row => fields.map(field => literal(row[field])));
  const lastRow = values.length + 5;
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.tabColor = "#253858";
  sheet.getRange(`A1:${lastColumn}${lastRow}`).format = {
    font: { name: "Arial", size: 10, color: "#202B3C" },
    verticalAlignment: "center", rowHeight: 28,
  };
  sheet.getRange("A2").values = [["Agnes · " + name]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#253858" };
  sheet.getRange(`A2:${lastColumn}2`).format.borders = { bottom: { style: "thin", color: "#A6B1C2" } };
  sheet.getRange("A3").values = [["导出日期（北京时间）"]];
  sheet.getRange("B3").values = [[new Date(`${payload.exported_date}T00:00:00Z`)]];
  sheet.getRange("B3").setNumberFormat("yyyy-mm-dd");
  sheet.getRange("E3").values = [[rows.some(row => row["邮箱密码"]) ? "含邮箱密码" : ""]];
  sheet.getRange("E3").format.font.color = "#7A4B10";
  sheet.getRange("F3").values = [[`${rows.length} 个邮箱`]];
  sheet.getRange(`A5:${lastColumn}5`).values = [headers];
  sheet.getRange(`A6:${lastColumn}${lastRow}`).setNumberFormat("@");
  sheet.getRange(`A6:${lastColumn}${lastRow}`).values = values;
  const table = sheet.tables.add(`A5:${lastColumn}${lastRow}`, true, tableName);
  table.showFilterButton = true;
  sheet.getRange(`A5:${lastColumn}5`).format = {
    fill: "#253858", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center", verticalAlignment: "center", rowHeight: 30,
    borders: { insideVertical: { style: "thin", color: "#FFFFFF" } },
  };
  for (let row = 6; row <= lastRow; row++) {
    sheet.getRange(`A${row}:${lastColumn}${row}`).format.fill = row % 2 ? "#F3F5F8" : "#FFFFFF";
  }
  if (payload.proxy_test) {
    for (const column of ["G", "H", "I", "J"]) sheet.getRange(`${column}1:${column}${lastRow}`).format.columnWidth = 24;
  }
  for (const [column, width] of Object.entries({ A: 43, B: 23, C: 38, D: 48, E: 23, F: 65 })) {
    sheet.getRange(`${column}1:${column}${lastRow}`).format.columnWidth = width;
  }
  sheet.getRange(`D6:D${lastRow}`).format.wrapText = true;
  sheet.getRange(`B6:C${lastRow}`).format.wrapText = true;
  sheet.getRange(`F6:F${lastRow}`).format.wrapText = true;
  sheet.getRange(`A6:${lastColumn}${lastRow}`).format.autofitRows();
  sheet.getRange(`E6:E${lastRow}`).conditionalFormats.add("containsText", {
    text: "无法注册", format: { fill: "#FFF1E8", font: { color: "#944B15" } },
  });
  sheet.getRange(`E6:E${lastRow}`).conditionalFormats.add("containsText", {
    text: "已完成", format: { fill: "#E8F2EC", font: { color: "#286346" } },
  });
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(1);
  sheets.push({ sheet, lastRow, values });
}

const complete = payload.rows.filter(row => row["状态"] === "已完成");
const remaining = payload.rows.filter(row => row["状态"] !== "已完成");
if (complete.length) {
  addSheet("已完成账号", complete, "AgnesComplete");
  if (remaining.length) addSheet("未完成记录", remaining, "AgnesRemaining");
} else {
  addSheet("开户结果", payload.rows, "AgnesAccounts");
}
workbook.recalculate();
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
for (const { sheet, lastRow, values } of sheets) {
  if (!same(sheet.getRange(`A6:${lastColumn}${lastRow}`).values, values)) throw new Error("DataMismatch");
}
await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!",
  options: { useRegex: true, maxResults: 10 }, maxChars: 1000,
});

// 预览隐藏凭证；交付文件保留用户请求的原始值。
for (const item of sheets) {
  item.credentialRange = item.sheet.getRange(`B6:D${item.lastRow}`);
  item.credentials = item.credentialRange.values;
  item.credentialRange.values = item.credentials.map(row => row.map(value => value ? "[已隐藏]" : ""));
}
workbook.recalculate();
await fs.mkdir(path.dirname(output), { recursive: true });
const previews = [];
for (const { sheet, range } of summarySheets) {
  const preview = await workbook.render({ sheetName: sheet.name, range, scale: 1.2 });
  const previewPath = path.join(path.dirname(output), "preview-proxy-summary.png");
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  previews.push(previewPath);
}
for (let index = 0; index < sheets.length; index++) {
  const { sheet, lastRow } = sheets[index];
  const preview = await workbook.render({
    sheetName: sheet.name, range: `A1:${lastColumn}${Math.min(lastRow, 25)}`, scale: 1.4,
  });
  const previewPath = path.join(path.dirname(output), `preview-redacted-${index + 1}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  previews.push(previewPath);
}
for (const item of sheets) item.credentialRange.values = item.credentials;
workbook.recalculate();
for (const { sheet, lastRow, values } of sheets) {
  if (!same(sheet.getRange(`A6:${lastColumn}${lastRow}`).values, values)) {
    throw new Error("CredentialRestoreMismatch");
  }
}
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(output);
await fs.unlink(output + ".inspect.ndjson").catch(error => {
  if (error.code !== "ENOENT") throw error;
});
console.log(JSON.stringify({
  output, rows: payload.rows.length, keys: payload.rows.filter(row => Boolean(row["API Key"])).length,
  previews,
}));
