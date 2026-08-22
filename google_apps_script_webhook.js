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

const TEAM_FULL_NAMES = {
  1: "Arsenal", 2: "Aston Villa", 3: "Bournemouth", 4: "Brentford", 5: "Brighton",
  6: "Chelsea", 7: "Coventry", 8: "Crystal Palace", 9: "Everton", 10: "Fulham",
  11: "Hull", 12: "Ipswich", 13: "Leeds", 14: "Liverpool", 15: "Man City",
  16: "Man Utd", 17: "Newcastle", 18: "Nott'm Forest", 19: "Tottenham", 20: "Sunderland"
};

function doPost(e) {
  return handleTelegramWebhook(e);
}

function handleTelegramWebhook(e) {
  try {
    const update = JSON.parse(e.postData.contents);
    if (!update.message || !update.message.text) return HtmlService.createHtmlOutput("OK");

    const chatId = update.message.chat.id;
    const text = update.message.text.trim();
    const textLower = text.toLowerCase();
    const cleanCmd = textLower.replace(/^\//, "").trim();

    // 1. AĞIR MOTOR & ÇÖZÜCÜ KOMUTLARI (GitHub Actions Tetikler + Anında Geri Bildirim)
    if (
      cleanCmd === "analiz" || cleanCmd === "kadrom" || cleanCmd === "taktik" ||
      cleanCmd === "optimal" || cleanCmd === "ruyatimi" || cleanCmd === "rüya takım" || cleanCmd === "ruya takim" || cleanCmd === "wildcard" ||
      textLower.includes("rüya takım ile değiştir") || textLower.includes("kadroyu optimal") || textLower.includes("kadromu rüya") ||
      textLower.startsWith("/transfer") || textLower.startsWith("transfer") || textLower.includes("yerine") ||
      textLower.startsWith("/kadro")
    ) {
      if (cleanCmd === "optimal" || cleanCmd === "ruyatimi" || cleanCmd === "rüya takım" || cleanCmd === "ruya takim" || cleanCmd === "wildcard") {
        sendTelegramMessage(chatId, "✨ <b>Rüya Takım (Optimal 15) hesaplanıyor...</b>\n<i>590 oyuncu arasından £100m bütçeyle en yüksek xP'li 15 çözülüyor (~10 sn).</i>");
      } else if (textLower.startsWith("/transfer") || textLower.startsWith("transfer") || textLower.includes("yerine")) {
        sendTelegramMessage(chatId, "🔄 <b>Transfer isteğiniz işleniyor...</b>");
      } else if (textLower.startsWith("/kadro")) {
        sendTelegramMessage(chatId, "📋 <b>15 kişilik kadronuz kaydediliyor...</b>");
      } else if (textLower.includes("rüya takım ile değiştir") || textLower.includes("kadroyu optimal")) {
        sendTelegramMessage(chatId, "📋 <b>Kadro güncelleme başlatıldı...</b>");
      } else {
        sendTelegramMessage(chatId, "🧠 <b>FPL Tam Strateji Analizi başlatıldı...</b>\n<i>Matematiksel çözücü ve FPL Review projeksiyonları hesaplanıyor (~35 sn).</i>");
      }
      triggerGitHubActions(text, chatId);
      return HtmlService.createHtmlOutput("OK");
    }

    // 2. ANLIK RAPORLAR (⚡ 0.2 sn - fpl_analysis.json veya kullanıcı analiz havuzundan çeker)
    const data = fetchAnalysisJson(chatId);
    if (data) {
      // Önce Python tarafından fpl_analysis.json içine gömülen güncel rapor havuzuna bak
      if (data.reports && typeof data.reports === "object") {
        if (data.reports[cleanCmd]) {
          sendTelegramMessage(chatId, data.reports[cleanCmd]);
          return HtmlService.createHtmlOutput("OK");
        }
        
        // Komut takma adları (Aliases)
        const aliasMap = {
          "help": "yardim", "komutlar": "yardim", "yardım": "yardim",
          "fikstur": "maclar", "fikstür": "maclar", "program": "maclar", "maçlar": "maclar", "maclar": "maclar", "maç programı": "maclar", "mac programi": "maclar", "haftanın maçları": "maclar", "haftanin maclari": "maclar", "/haftalikmaclar": "maclar",
          "c kim": "kaptan", "captain": "kaptan", "kime verelim": "kaptan",
          "revir": "sakatlar", "saglik": "sakatlar", "sağlık": "sakatlar", "injury": "sakatlar",
          "kolay maçlar": "salincak", "kolay fikstür": "salincak", "swings": "salincak", "kolayfikstur": "salincak", "kolayfikstür": "salincak",
          "fiyatlar": "fiyat", "price": "fiyat", "zam": "fiyat", "düşüş": "fiyat"
        };
        const mappedKey = aliasMap[cleanCmd] || aliasMap[textLower];
        if (mappedKey && data.reports[mappedKey]) {
          sendTelegramMessage(chatId, data.reports[mappedKey]);
          return HtmlService.createHtmlOutput("OK");
        }
      }

      // Güvenlik yedeği (Fallback formatlayıcılar)
      if (cleanCmd === "yardim" || cleanCmd === "help" || cleanCmd === "yardım") {
        sendTelegramMessage(chatId, getHelpText());
        return HtmlService.createHtmlOutput("OK");
      }
      if (cleanCmd === "maclar" || cleanCmd === "maçlar" || cleanCmd === "fikstur" || cleanCmd === "fikstür" || cleanCmd === "program") {
        sendTelegramMessage(chatId, formatMatchesReport(data));
        return HtmlService.createHtmlOutput("OK");
      }
      if (cleanCmd === "kaptan") {
        sendTelegramMessage(chatId, formatCaptainReport(data));
        return HtmlService.createHtmlOutput("OK");
      }
      if (cleanCmd === "sakatlar" || cleanCmd === "revir") {
        sendTelegramMessage(chatId, formatHealthReport(data));
        return HtmlService.createHtmlOutput("OK");
      }
      if (cleanCmd === "salincak") {
        sendTelegramMessage(chatId, formatFixtureReport(data));
        return HtmlService.createHtmlOutput("OK");
      }
      if (cleanCmd === "fiyat") {
        sendTelegramMessage(chatId, formatPriceReport(data));
        return HtmlService.createHtmlOutput("OK");
      }
    }

    // 3. TANINMAYAN KOMUT (Varsayılan Rehber)
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

function getGitHubToken() {
  const prop = PropertiesService.getScriptProperties().getProperty("GITHUB_PAT");
  if (prop && prop.trim().length > 10) return prop.trim();
  return GITHUB_PAT;
}

function triggerGitHubActions(teamDataText, chatId) {
  const token = getGitHubToken();
  if (!token || token === "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN") {
    if (chatId) {
      sendTelegramMessage(chatId, "⚠️ <b>Hata:</b> Google Apps Script içinde GITHUB_PAT (GitHub Token) tanımlı değil. Lütfen Script Properties'e GITHUB_PAT ekleyin.");
    }
    Logger.log("GITHUB_PAT tanımlı değil.");
    return null;
  }
  const url = `https://api.github.com/repos/${GITHUB_REPO}/dispatches`;
  const payload = {
    event_type: "telegram-trigger",
    client_payload: {
      team_data: teamDataText,
      chat_id: String(chatId || "")
    }
  };
  const options = {
    method: "post",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "GAS-Telegram-Bridge",
      "X-GitHub-Api-Version": "2022-11-28"
    },
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  const res = UrlFetchApp.fetch(url, options);
  const code = res.getResponseCode();
  Logger.log("GitHub Dispatch Response Code: " + code);
  if (code !== 204) {
    Logger.log("GitHub Dispatch Error: " + res.getContentText());
    if (chatId) {
      sendTelegramMessage(chatId, `⚠️ <b>GitHub Tetikleme Hatası (${code}):</b> ${res.getContentText() || 'GitHub yetkisi reddedildi.'}`);
    }
  }
  return res;
}

// Test fonksiyonu: GitHub bağlantısını doğrudan doğrulamak için bunu Apps Script'ten çalıştırabilirsiniz.
function testGitHubDispatch() {
  const res = triggerGitHubActions("/analiz");
  if (res) {
    Logger.log("Test HTTP Response Code: " + res.getResponseCode());
    Logger.log("Test Response Body: " + res.getContentText());
  }
}

function fetchAnalysisJson(chatId) {
  if (chatId) {
    try {
      const userUrl = `https://raw.githubusercontent.com/${GITHUB_REPO}/main/data/users/analysis_${chatId}.json?t=${new Date().getTime()}`;
      const res = UrlFetchApp.fetch(userUrl, { muteHttpExceptions: true });
      if (res.getResponseCode() === 200) {
        return JSON.parse(res.getContentText());
      }
    } catch (e) {
      Logger.log("fetchUserAnalysisJson error: " + e);
    }
  }
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
    "🔹 <b>/maclar</b> (veya <b>/fikstur</b>) ➔ O haftanın tüm Premier League maç takvimi, gün ve saatleri (TSİ).",
    "🔹 <b>/optimal</b> ➔ £100m bütçe ile en ideal 15 kişilik Rüya Takım.",
    "🔹 <b>/kaptan</b> ➔ O haftanın en iyi 2 kaptan tercihi ve patlama indeksi.",
    "🔹 <b>/sakatlar</b> ➔ Kadronuzdaki şüpheli/sakat oyuncuların sağlık raporu.",
    "🔹 <b>/salincak</b> ➔ Önümüzdeki 5 hafta fikstürü en çok kolaylaşan takımlar.",
    "🔹 <b>/fiyat</b> ➔ Önümüzdeki 5 gün içinde beklenen yüksek ve orta ihtimalli fiyat değişim radarı.",
    "🔹 <b>/transfer [Çıkan] yerine [Giren]</b> ➔ Kadroda oyuncu değiştirir.",
    "🔹 <b>/yardim</b> ➔ Bu komut listesini getirir."
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
  return lines.join("\n");
}

function formatPriceReport(payload) {
  const alerts = payload.price_alerts || [];
  let lines = [];
  lines.push("💰 <b>5 GÜNLÜK FİYAT DEĞİŞİM RADARI</b>");
  lines.push("<i>Önümüzdeki 5 günlük transfer trendi ve fiyat değişim olasılıkları:</i>\n");
  
  if (!alerts || alerts.length === 0) {
    lines.push("📊 Önümüzdeki 5 gün için piyasada kritik bir fiyat değişimi riski veya fırsatı bulunmuyor.\n");
    return lines.join("\n");
  }

  const rises = alerts.filter(a => a.direction === "rise");
  const falls = alerts.filter(a => a.direction === "fall");

  lines.push("📈 <b>FİYAT ARTIŞI BEKLENENLER (+£0.1m)</b>");
  const highRises = rises.filter(a => a.likelihood === "high" || (a.probability_1d || 0) >= 0.80 || (a.probability || 0) >= 0.85);
  const medRises = rises.filter(a => !highRises.includes(a) && (a.probability || 0) >= 0.45);

  if (highRises.length > 0) {
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün / Bu Gece):</b>");
    for (let i = 0; i < Math.min(highRises.length, 5); i++) {
      const a = highRises[i];
      const pName = a.web_name || a.name || "Oyuncu";
      const tId = a.team || a.team_id;
      const teamStr = TEAM_NAMES[tId] ? ` (${TEAM_NAMES[tId]})` : "";
      const priceStr = a.price ? `£${Number(a.price).toFixed(1)}m` : "";
      const prob = Math.round((a.probability || 0) * 100);
      const squadFlag = a.in_squad ? " 👤 <i>(Kadronuzda)</i>" : "";
      lines.push(`  • <b>${pName}${teamStr}</b> - ${priceStr} ➔ <b>%${prob}</b>${squadFlag}`);
    }
  } else {
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün / Bu Gece):</b> <i>Acil artış adayı yok</i>");
  }

  if (medRises.length > 0) {
    lines.push("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b>");
    for (let i = 0; i < Math.min(medRises.length, 5); i++) {
      const a = medRises[i];
      const pName = a.web_name || a.name || "Oyuncu";
      const tId = a.team || a.team_id;
      const teamStr = TEAM_NAMES[tId] ? ` (${TEAM_NAMES[tId]})` : "";
      const priceStr = a.price ? `£${Number(a.price).toFixed(1)}m` : "";
      const prob = Math.round((a.probability || 0) * 100);
      const squadFlag = a.in_squad ? " 👤 <i>(Kadronuzda)</i>" : "";
      lines.push(`  • <b>${pName}${teamStr}</b> - ${priceStr} ➔ <b>%${prob}</b>${squadFlag}`);
    }
  } else {
    lines.push("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b> <i>Trend takibinde olan oyuncu yok</i>");
  }
  lines.push("");

  lines.push("📉 <b>FİYAT DÜŞÜŞÜ BEKLENENLER (-£0.1m)</b>");
  const highFalls = falls.filter(a => a.likelihood === "high" || (a.probability_1d || 0) >= 0.80 || (a.probability || 0) >= 0.85);
  const medFalls = falls.filter(a => !highFalls.includes(a) && (a.probability || 0) >= 0.45);

  if (highFalls.length > 0) {
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün / Bu Gece):</b>");
    for (let i = 0; i < Math.min(highFalls.length, 5); i++) {
      const a = highFalls[i];
      const pName = a.web_name || a.name || "Oyuncu";
      const tId = a.team || a.team_id;
      const teamStr = TEAM_NAMES[tId] ? ` (${TEAM_NAMES[tId]})` : "";
      const priceStr = a.price ? `£${Number(a.price).toFixed(1)}m` : "";
      const prob = Math.round((a.probability || 0) * 100);
      const squadFlag = a.in_squad ? " 👤 <i>(Kadronuzda!)</i>" : "";
      lines.push(`  • <b>${pName}${teamStr}</b> - ${priceStr} ➔ <b>%${prob}</b>${squadFlag}`);
    }
  } else {
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün / Bu Gece):</b> <i>Acil düşüş adayı yok</i>");
  }

  if (medFalls.length > 0) {
    lines.push("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b>");
    for (let i = 0; i < Math.min(medFalls.length, 5); i++) {
      const a = medFalls[i];
      const pName = a.web_name || a.name || "Oyuncu";
      const tId = a.team || a.team_id;
      const teamStr = TEAM_NAMES[tId] ? ` (${TEAM_NAMES[tId]})` : "";
      const priceStr = a.price ? `£${Number(a.price).toFixed(1)}m` : "";
      const prob = Math.round((a.probability || 0) * 100);
      const squadFlag = a.in_squad ? " 👤 <i>(Kadronuzda!)</i>" : "";
      lines.push(`  • <b>${pName}${teamStr}</b> - ${priceStr} ➔ <b>%${prob}</b>${squadFlag}`);
    }
  } else {
    lines.push("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b> <i>Düşüş baskısında olan oyuncu yok</i>");
  }

  lines.push("\n💡 <b>Strateji Tavsiyesi:</b>");
  lines.push("<i>Kadro değerini korumak için yüksek ihtimalli düşüş adaylarını erken elden çıkarmayı, transfer hedeflerinizi ise sakatlık riski yoksa fiyat artmadan almayı değerlendirin.</i>");
  
  return lines.join("\n");
}

function formatMatchesReport(payload) {
  if (payload.matches_report) {
    return payload.matches_report;
  }
  
  const fixtures = payload.fixtures || [];
  const meta = payload.meta || {};
  const gw = payload.fixture_gw || meta.fixture_gw || meta.current_gw || 1;
  
  if (fixtures.length === 0) {
    return `⚠️ GW${gw} için fikstür verisi bulunamadı.`;
  }
  
  const MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  const DAYS_TR = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];
  
  const grouped = {};
  for (const f of fixtures) {
    if (!f.kickoff_time) continue;
    const d = new Date(f.kickoff_time);
    const trDate = new Date(d.getTime() + (3 * 60 * 60 * 1000));
    
    const dayName = DAYS_TR[trDate.getUTCDay()];
    const dayNum = trDate.getUTCDate();
    const monthName = MONTHS_TR[trDate.getUTCMonth()];
    const dayKey = `${dayNum} ${monthName} ${dayName}`;
    
    const hours = String(trDate.getUTCHours()).padStart(2, '0');
    const minutes = String(trDate.getUTCMinutes()).padStart(2, '0');
    const timeStr = `${hours}:${minutes}`;
    
    if (!grouped[dayKey]) {
      grouped[dayKey] = [];
    }
    grouped[dayKey].push({
      time: timeStr,
      fixture: f
    });
  }
  
  let lines = [];
  lines.push(`🦁 <b>PREMIER LEAGUE GW${gw} MAÇ PROGRAMI (TSİ)</b>\n`);
  
  for (const [dayKey, list] of Object.entries(grouped)) {
    lines.push(`🗓️ <b>${dayKey}</b>`);
    for (const item of list) {
      const f = item.fixture;
      const hTeam = f.team_h_name || TEAM_FULL_NAMES[f.team_h] || `Takım ${f.team_h}`;
      const aTeam = f.team_a_name || TEAM_FULL_NAMES[f.team_a] || `Takım ${f.team_a}`;
      
      if (f.finished && f.team_h_score !== null && f.team_a_score !== null) {
        lines.push(`• <b>${item.time}</b> ➔ ${hTeam} <b>${f.team_h_score} - ${f.team_a_score}</b> ${aTeam} (MS)`);
      } else if (f.started && f.team_h_score !== null && f.team_a_score !== null) {
        lines.push(`• <b>${item.time}</b> ➔ ${hTeam} <b>${f.team_h_score} - ${f.team_a_score}</b> ${aTeam} (🔴 Canlı)`);
      } else {
        lines.push(`• <b>${item.time}</b> ➔ <b>${hTeam}</b> vs <b>${aTeam}</b>`);
      }
    }
    lines.push("");
  }
  
  lines.push("⏰ <i>Tüm başlama saatleri Türkiye saati (TSİ / GMT+3) ile verilmiştir.</i>");
  return lines.join("\n");
}
