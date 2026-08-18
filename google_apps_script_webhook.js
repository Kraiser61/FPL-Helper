// ============================================================================
// 🦁 FPL HELPER - GOOGLE APPS SCRIPT TELEGRAM BOT WEBHOOK ROUTER
// ============================================================================
// Bu kodu script.google.com üzerindeki projenize yapıştırıp "Yeni Dağıtım (New Deployment)"
// olarak Web App şeklinde yayınlayabilirsiniz.

const BOT_TOKEN = "8315284284:AAF4HjtfP1kW5rNUPRe5n1J1KBg4PsT83Jg";
const GITHUB_REPO = "Kraiser61/FPL-Helper";
const GITHUB_PAT = PropertiesService.getScriptProperties().getProperty("GITHUB_PAT") || "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN";

const TEAM_NAMES = {
  1: "ARS", 2: "AVL", 3: "BOU", 4: "BRE", 5: "BHA",
  6: "CHE", 7: "COV", 8: "CRY", 9: "EVE", 10: "FUL",
  11: "HUL", 12: "IPS", 13: "LEE", 14: "LIV", 15: "MCI",
  16: "MUN", 17: "NEW", 18: "NFO", 19: "TOT", 20: "SUN"
};

function doPost(e) {
  try {
    const update = JSON.parse(e.postData.contents);
    if (!update.message || !update.message.text) return HtmlService.createHtmlOutput("OK");

    const chatId = update.message.chat.id;
    const text = update.message.text.trim();
    const textLower = text.toLowerCase();

    // 1. YARDIM / HELP (⚡ 0.1 sn)
    if (textLower === "/yardim" || textLower === "/help" || textLower === "yardim" || textLower === "help" || textLower === "komutlar") {
      sendTelegramMessage(chatId, getHelpText());
      return HtmlService.createHtmlOutput("OK");
    }

    // 2. ANLIK ÖNBELLEK KOMUTLARI (⚡ 0.3 sn - GitHub Actions çalıştırmaz)
    if (textLower === "/kaptan" || textLower === "kaptan" || textLower === "c kim") {
      const data = fetchAnalysisJson();
      if (data && data.lineup) {
        sendTelegramMessage(chatId, formatCaptainReport(data));
      } else {
        sendTelegramMessage(chatId, "⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.");
      }
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower === "/sakatlar" || textLower === "/revir" || textLower === "sakatlar" || textLower === "revir" || textLower === "sağlık" || textLower === "saglik") {
      const data = fetchAnalysisJson();
      if (data && data.squad_health) {
        sendTelegramMessage(chatId, formatHealthReport(data));
      } else {
        sendTelegramMessage(chatId, "⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.");
      }
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower === "/fikstur" || textLower === "/fikstür" || textLower === "fikstur" || textLower === "fikstür" || textLower === "kolay maçlar") {
      const data = fetchAnalysisJson();
      if (data && data.fixture_swings) {
        sendTelegramMessage(chatId, formatFixtureReport(data));
      } else {
        sendTelegramMessage(chatId, "⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.");
      }
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower === "/fiyat" || textLower === "fiyat" || textLower === "fiyatlar" || textLower === "zam") {
      const data = fetchAnalysisJson();
      if (data && data.price_alerts) {
        sendTelegramMessage(chatId, formatPriceReport(data));
      } else {
        sendTelegramMessage(chatId, "⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.");
      }
      return HtmlService.createHtmlOutput("OK");
    }

    // 3. AĞIR MOTOR / ÇÖZÜCÜ KOMUTLARI (GitHub Actions Tetikler + Özel Bildirim)
    if (textLower === "/analiz" || textLower === "analiz" || textLower === "kadrom" || textLower === "taktik") {
      sendTelegramMessage(chatId, "🧠 <b>FPL Tam Strateji Analizi başlatıldı...</b>\n<i>Matematiksel çözücü ve FPL Review projeksiyonları hesaplanıyor (~35 sn).</i>");
      triggerGitHubActions(text);
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower === "/optimal" || textLower === "/ruyatimi" || textLower === "optimal" || textLower === "rüya takım" || textLower === "ruya takim" || textLower === "wildcard") {
      sendTelegramMessage(chatId, "✨ <b>Rüya Takım (Optimal 15) hesaplanıyor...</b>\n<i>590 oyuncu arasından £100m bütçeyle en yüksek xP'li 15 çözülüyor (~10 sn).</i>");
      triggerGitHubActions(text);
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower.includes("rüya takım ile değiştir") || textLower.includes("kadroyu optimal") || textLower.includes("kadromu rüya")) {
      sendTelegramMessage(chatId, "📋 <b>Kadro güncelleme başlatıldı...</b>");
      triggerGitHubActions(text);
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower.startsWith("/transfer") || textLower.startsWith("transfer") || textLower.includes("yerine")) {
      sendTelegramMessage(chatId, "🔄 <b>Transfer isteğiniz işleniyor...</b>");
      triggerGitHubActions(text);
      return HtmlService.createHtmlOutput("OK");
    }

    if (textLower.startsWith("/kadro")) {
      sendTelegramMessage(chatId, "📋 <b>15 kişilik kadronuz kaydediliyor...</b>");
      triggerGitHubActions(text);
      return HtmlService.createHtmlOutput("OK");
    }

    // Tanınmayan komut
    sendTelegramMessage(chatId, "🤖 <b>Komut anlaşılamadı.</b> Mevcut komutlar için <b>/yardim</b> yazabilirsiniz.");

  } catch (err) {
    Logger.log("Hata: " + err);
  }
  return HtmlService.createHtmlOutput("OK");
}

function sendTelegramMessage(chatId, text) {
  const url = `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`;
  const payload = {
    chat_id: chatId,
    text: text,
    parse_mode: "HTML"
  };
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

function triggerGitHubActions(teamDataText) {
  const url = `https://api.github.com/repos/${GITHUB_REPO}/dispatches`;
  const payload = {
    event_type: "telegram-trigger",
    client_payload: {
      team_data: teamDataText
    }
  };
  const options = {
    method: "post",
    headers: {
      "Authorization": `Bearer ${GITHUB_PAT}`,
      "Accept": "application/vnd.github.v3+json",
      "User-Agent": "GAS-Telegram-Bridge"
    },
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  UrlFetchApp.fetch(url, options);
}

function fetchAnalysisJson() {
  try {
    const rawUrl = `https://raw.githubusercontent.com/${GITHUB_REPO}/main/data/fpl_analysis.json?t=${new Date().getTime()}`;
    const res = UrlFetchApp.fetch(rawUrl, { muteHttpExceptions: true });
    if (res.getResponseCode() === 200) {
      return JSON.parse(res.getContentText());
    }
  } catch (e) {
    Logger.log("fetchAnalysisJson error: " + e);
  }
  return null;
}

function getHelpText() {
  return [
    "📖 <b>FPL AI BOT KOMUT REHBERİ</b>\n",
    "🔹 <b>/analiz</b> ➔ Tam strateji ve 11 raporu (Kaptan, Transfer, Çip, Diziliş).",
    "🔹 <b>/optimal</b> ➔ £100m bütçe ile en ideal 15 kişilik Rüya Takım.",
    "🔹 <b>/kaptan</b> ➔ O haftanın en iyi 2 kaptan tercihi ve patlama indeksi.",
    "🔹 <b>/sakatlar</b> ➔ Kadronuzdaki şüpheli/sakat oyuncuların sağlık raporu.",
    "🔹 <b>/fikstur</b> ➔ Önümüzdeki 5 hafta fikstürü en çok kolaylaşan takımlar.",
    "🔹 <b>/fiyat</b> ➔ Gece fiyatı artması/düşmesi beklenen oyuncu alarmları.",
    "🔹 <b>/transfer [Çıkan] yerine [Giren]</b> ➔ Kadroda oyuncu değiştirir.",
    "🔹 <b>/yardim</b> ➔ Bu komut listesini getirir.\n",
    "🤖 <i>Kraiser61 AI Engine</i>"
  ].join("\n");
}

function formatCaptainReport(payload) {
  const meta = payload.meta || {};
  const gw = meta.current_gw || 1;
  const lineup = payload.lineup || {};
  const cap = lineup.captain || {};
  const vc = lineup.vice_captain || {};
  
  let lines = [];
  lines.push(`👑 <b>KAPTAN & DİFERANSİYEL RADARI (GW${gw})</b>\n`);
  if (cap.name) {
    const cName = cap.name;
    const cTeam = cap.team || "";
    const cXp = (cap.xp_next_gw || 0).toFixed(1);
    const cXpCap = (cXp * 2).toFixed(1);
    const cBoom = (cap.boom_index || 0).toFixed(1);
    lines.push(`🥇 <b>1. Kaptan Tercihi:</b> ${cName} (${cTeam})`);
    lines.push(`   • Beklenen Puan: <b>${cXp} xP</b> (Kaptanlık: <b>${cXpCap} xP</b>)`);
    lines.push(`   • Patlama İndeksi: <b>${cBoom}/10</b>\n`);
  }
  if (vc.name) {
    const vName = vc.name;
    const vTeam = vc.team || "";
    const vXp = (vc.xp_next_gw || 0).toFixed(1);
    lines.push(`🥈 <b>2. Kaptan (Yedek):</b> ${vName} (${vTeam}) - <b>${vXp} xP</b>\n`);
  }
  lines.push("🤖 <i>Kraiser61 AI Engine</i>");
  return lines.join("\n");
}

function formatHealthReport(payload) {
  const health = payload.squad_health || [];
  let lines = [];
  lines.push("🏥 <b>KADRO SAĞLIK & REVİR RADARI</b>\n");
  if (health.length > 0) {
    lines.push("⚠️ <b>Şüpheli veya Sakat Oyuncularınız:</b>");
    for (const h of health) {
      const name = h.web_name || "Oyuncu";
      const chance = h.chance !== null && h.chance !== undefined ? `%${h.chance}` : "Belirsiz";
      const news = h.news || "Sağlık durumu takip ediliyor.";
      const emoji = h.chance === 0 ? "🔴" : "🟡";
      lines.push(`  ${emoji} <b>${name}:</b> ${chance} (${news})`);
    }
    lines.push("");
  } else {
    lines.push("✅ Kadronuzda sakat veya cezalı oyuncu bulunmuyor. Tüm ilk 11 ve yedekler hazır!\n");
  }
  lines.push("🤖 <i>Kraiser61 AI Engine</i>");
  return lines.join("\n");
}

function formatFixtureReport(payload) {
  const swings = payload.fixture_swings || [];
  let lines = [];
  lines.push("📅 <b>FİKSTÜR SALINCAK ANALİZİ (ÖNÜMÜZDEKİ 5 HAFTA)</b>\n");
  if (swings.length > 0) {
    lines.push("🟢 <b>Fikstürü En Çok Kolaylaşan Takımlar:</b>");
    for (let i = 0; i < Math.min(swings.length, 5); i++) {
      const item = swings[i];
      const tName = item.team_name || TEAM_NAMES[item.team_id] || `Takım ${item.team_id}`;
      const near = (item.near_fdr || 2.5).toFixed(1);
      const far = (item.far_fdr || 3.5).toFixed(1);
      lines.push(`  ${i+1}. <b>${tName}</b> ➔ Yakın Zorluk: <b>${near}</b> | İleri: <b>${far}</b>`);
    }
    lines.push("");
  } else {
    lines.push("📊 Önümüzdeki 5 hafta için dengeli bir fikstür dağılımı mevcut.\n");
  }
  lines.push("🤖 <i>Kraiser61 AI Engine</i>");
  return lines.join("\n");
}

function formatPriceReport(payload) {
  const alerts = payload.price_alerts || [];
  let lines = [];
  lines.push("💰 <b>FİYAT DEĞİŞİM RADARI (BU GECE)</b>\n");
  if (alerts.length > 0) {
    lines.push("📊 <b>Fiyat Değişim Riski/Fırsatı Olan Oyuncular:</b>");
    for (let i = 0; i < Math.min(alerts.length, 6); i++) {
      const a = alerts[i];
      const pName = a.web_name || a.name || "Oyuncu";
      const change = a.type || "artış/düşüş";
      const tId = a.team || a.team_id;
      const teamStr = TEAM_NAMES[tId] ? ` (${TEAM_NAMES[tId]})` : "";
      lines.push(`  • <b>${pName}${teamStr}</b>: ${change}`);
    }
    lines.push("");
  } else {
    lines.push("📈 Bu gece kadronuzu etkileyen kritik bir fiyat değişimi riski bulunmuyor.\n");
  }
  lines.push("🤖 <i>Kraiser61 AI Engine</i>");
  return lines.join("\n");
}
