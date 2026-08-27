// ============================================================================
// 🦁 FPL HELPER - GOOGLE APPS SCRIPT TELEGRAM BOT WEBHOOK ROUTER (DYNAMIC CONFIG)
// ============================================================================
// Bu kod GitHub üzerinden dinamik yapılandırma (data/bot_config.json) çeker.
// Bir kez deploy edildikten sonra mesajlar ve süreler GitHub'dan otomatik güncellenir.

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

function fetchBotConfig() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get("bot_config_json");
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch (e) {}
  }
  try {
    const url = `https://raw.githubusercontent.com/${GITHUB_REPO}/main/data/bot_config.json?t=${new Date().getTime()}`;
    const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (res.getResponseCode() === 200) {
      const cfgText = res.getContentText();
      cache.put("bot_config_json", cfgText, 60); // 1 dakika önbellek
      return JSON.parse(cfgText);
    }
  } catch (e) {
    Logger.log("fetchBotConfig error: " + e);
  }
  // Güvenli varsayılan fallback
  return {
    wait_messages: {
      optimal: "✨ <b>Rüya Takım hesaplanıyor...</b>\n<i>En ideal 15 kişilik kadro hesaplanıyor (50-65 sn).</i>",
      analiz: "🧠 <b>Strateji analizi başlatıldı...</b>\n<i>Haftalık kadro ve transfer analizi hazırlanıyor (75-85 sn).</i>",
      transfer: "🔄 <b>Transfer isteğiniz işleniyor...</b>",
      ft: "⚙️ <b>Serbest transfer hakkınız güncelleniyor...</b>",
      kadro: "📋 <b>15 kişilik kadronuz kaydediliyor...</b>",
      adopt_dream_team: "📋 <b>Kadro güncelleme başlatıldı...</b>"
    },
    help_text: "",
    unrecognized_command: "🤖 <b>Komut anlaşılamadı.</b> Mevcut komutlar için <b>/yardim</b> yazabilirsiniz."
  };
}

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

    const config = fetchBotConfig();
    const wm = (config && config.wait_messages) ? config.wait_messages : {};

    // 1. AĞIR MOTOR & ÇÖZÜCÜ KOMUTLARI (GitHub Actions Tetikler + Anında Geri Bildirim)
    let isActionCommand = false;
    let actionWaitKey = "analiz";

    // Dinamik Desen Eşleme (bot_config.json üzerinden canlı güncellenir)
    if (config && Array.isArray(config.github_dispatch_patterns)) {
      for (let i = 0; i < config.github_dispatch_patterns.length; i++) {
        try {
          const reg = new RegExp(config.github_dispatch_patterns[i], "i");
          if (reg.test(text) || reg.test(cleanCmd)) {
            isActionCommand = true;
            if (/optimal|ruya|rüya|wildcard/i.test(text)) actionWaitKey = "optimal";
            else if (/transfer|yerine/i.test(text)) actionWaitKey = "transfer";
            else if (/ft|hak/i.test(text)) actionWaitKey = "ft";
            else if (/kadro/i.test(text)) actionWaitKey = "kadro";
            break;
          }
        } catch (err) {}
      }
    }

    // Güvenlik Yedeği: Statik Eşleme
    if (!isActionCommand) {
      if (
        cleanCmd === "optimal" || cleanCmd === "ruyatimi" || cleanCmd === "rüya takım" || cleanCmd === "ruya takim" || cleanCmd === "wildcard" ||
        textLower.includes("rüya takım ile değiştir") || textLower.includes("kadroyu optimal") || textLower.includes("kadromu rüya") ||
        textLower.startsWith("/transfer") || textLower.startsWith("transfer") || textLower.includes("yerine") ||
        textLower.startsWith("/ft") || textLower.startsWith("ft") || cleanCmd === "ft" ||
        textLower.startsWith("/hak") || textLower.startsWith("hak") || cleanCmd === "hak" ||
        textLower.startsWith("/kadro") || textLower.startsWith("kadro") ||
        cleanCmd === "analiz" || cleanCmd === "kadrom" || cleanCmd === "taktik"
      ) {
        isActionCommand = true;
        if (cleanCmd === "optimal" || cleanCmd === "ruyatimi" || cleanCmd === "rüya takım" || cleanCmd === "ruya takim" || cleanCmd === "wildcard") actionWaitKey = "optimal";
        else if (textLower.startsWith("/transfer") || textLower.startsWith("transfer") || textLower.includes("yerine")) actionWaitKey = "transfer";
        else if (textLower.startsWith("/ft") || textLower.startsWith("ft") || textLower.startsWith("/hak") || textLower.startsWith("hak")) actionWaitKey = "ft";
        else if (textLower.startsWith("/kadro")) actionWaitKey = "kadro";
        else if (textLower.includes("rüya takım ile değiştir") || textLower.includes("kadroyu optimal")) actionWaitKey = "adopt_dream_team";
      }
    }

    if (isActionCommand) {
      const waitMsg = wm[actionWaitKey] || wm.analiz || "🧠 <b>Strateji analizi başlatıldı...</b>";
      sendTelegramMessage(chatId, waitMsg);
      triggerGitHubActions(text, chatId);
      return HtmlService.createHtmlOutput("OK");
    }

    // 2. YARDIM / KOMUT REHBERİ (Her zaman çalışır)
    if (cleanCmd === "yardim" || cleanCmd === "help" || cleanCmd === "yardım" || cleanCmd === "komutlar") {
      const helpMsg = (config && config.help_text) ? config.help_text : getHelpText();
      sendTelegramMessage(chatId, helpMsg);
      return HtmlService.createHtmlOutput("OK");
    }

    // 3. CANLI FİKSTÜR VE MAÇ PROGRAMI (⚡ Her sorguda doğrudan FPL API'den anlık canlı skor ve maç takvimi çeker)
    const matchCommands = [
      "maclar", "maçlar", "fikstur", "fikstür", "program", "maç programı", "mac programi", "haftanın maçları", "haftanin maclari", "/haftalikmaclar"
    ];
    if (matchCommands.includes(cleanCmd) || matchCommands.includes(textLower)) {
      sendTelegramMessage(chatId, fetchLiveFixturesReport());
      return HtmlService.createHtmlOutput("OK");
    }

    // 4. STRATEJİ VE ÖNBELLEK RAPORLARI (⚡ 2 saatlik tazelik kontrolü ile)
    const instantCommands = [
      "kaptan", "captain", "c kim", "kime verelim",
      "sakatlar", "revir", "saglik", "sağlık", "injury",
      "salincak", "salıncak", "swings", "kolayfikstur", "kolayfikstür", "kolay maçlar", "kolay fikstür",
      "fiyat", "price", "zam", "düşüş", "fiyatlar",
      "kadrom", "takim", "15", "oyuncular"
    ];

    const isInstantCmd = instantCommands.includes(cleanCmd) || instantCommands.includes(textLower);

    if (isInstantCmd) {
      const data = fetchAnalysisJson(chatId);
      if (!data) {
        sendTelegramMessage(chatId, "⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.");
        return HtmlService.createHtmlOutput("OK");
      }

      // 2 saatlik tazelik kuralı kontrolü
      if (!isAnalysisFresh(data, 2)) {
        sendTelegramMessage(chatId, getStaleDataMessage(data, config));
        return HtmlService.createHtmlOutput("OK");
      }

      // Rapor havuzuna bak
      if (data.reports && typeof data.reports === "object") {
        if (data.reports[cleanCmd]) {
          sendTelegramMessage(chatId, data.reports[cleanCmd]);
          return HtmlService.createHtmlOutput("OK");
        }
        
        // Komut takma adları (Aliases)
        const aliasMap = {
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

    // 5. TANINMAYAN KOMUT (Varsayılan Rehber)
    const unrecMsg = (config && config.unrecognized_command) ? config.unrecognized_command : "🤖 <b>Komut anlaşılamadı.</b> Mevcut komutlar için <b>/yardim</b> yazabilirsiniz.";
    sendTelegramMessage(chatId, unrecMsg);

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

function fetchAnalysisJson(chatId) {
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

function isAnalysisFresh(data, maxHours) {
  if (!data || !data.meta) return false;
  maxHours = maxHours || 2;
  var genTime = null;
  if (data.meta.generated_at_epoch) {
    genTime = data.meta.generated_at_epoch * 1000;
  } else if (data.meta.generated_at_iso) {
    genTime = new Date(data.meta.generated_at_iso).getTime();
  } else if (data.meta.generated_at) {
    var s = String(data.meta.generated_at).replace(" ", "T");
    genTime = new Date(s).getTime();
  }
  if (!genTime || isNaN(genTime)) return false;
  var now = new Date().getTime();
  var diffHours = (now - genTime) / (1000 * 60 * 60);
  return diffHours <= maxHours;
}

function getStaleDataMessage(data, config) {
  var timeText = "2 saatten önce";
  if (data && data.meta && data.meta.generated_at) {
    timeText = data.meta.generated_at;
  }
  if (config && config.stale_warning_template) {
    return config.stale_warning_template.replace("{time}", timeText);
  }
  return "⚠️ <b>Analiz Verileri Güncel Değil:</b>\n" +
         "Kayıtlı son analiz <b>" + timeText + "</b> tarihinde üretilmiş (2 saatlik geçerlilik süresi doldu).\n\n" +
         "En güncel transfer trendleri, sakatlıklar ve maç verileriyle yanıt alabilmek için lütfen önce <b>/analiz</b> komutunu çalıştırın.\n\n" +
         "<i>💡 <b>/analiz</b> ve <b>/optimal</b> komutları her zaman motoru canlı tetikleyerek verileri sıfırdan hesaplar.</i>";
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
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b>");
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
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b> <i>Acil artış adayı yok</i>");
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
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b>");
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
    lines.push("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b> <i>Acil düşüş adayı yok</i>");
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

function isFixtureFinished(f) {
  if (f.finished || f.finished_provisional || (f.minutes && f.minutes >= 90)) return true;
  if (f.started && f.kickoff_time) {
    var ko = new Date(f.kickoff_time);
    var now = new Date();
    if ((now.getTime() - ko.getTime()) > (110 * 60 * 1000)) return true;
  }
  return false;
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
      
      const finished = isFixtureFinished(f);
      if (finished && f.team_h_score !== null && f.team_a_score !== null) {
        lines.push(`• <b>${item.time}</b> ➔ ${hTeam} <b>${f.team_h_score} - ${f.team_a_score}</b> ${aTeam} (Bitti)`);
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

function fetchLiveFixturesReport() {
  try {
    const bootstrapRes = UrlFetchApp.fetch("https://fantasy.premierleague.com/api/bootstrap-static/", { muteHttpExceptions: true });
    if (bootstrapRes.getResponseCode() !== 200) {
      return "⚠️ FPL API'ye erişilemedi. Lütfen birazdan tekrar deneyin.";
    }
    const bootstrap = JSON.parse(bootstrapRes.getContentText());
    const events = bootstrap.events || [];
    const teams = bootstrap.teams || [];
    const teamFullNames = {};
    for (const t of teams) {
      teamFullNames[t.id] = t.name;
    }

    let currentEvent = events.find(e => e.is_current);
    let nextEvent = events.find(e => e.is_next);
    let gw = 1;

    if (currentEvent && !currentEvent.finished) {
      gw = currentEvent.id;
    } else if (nextEvent) {
      gw = nextEvent.id;
    } else if (currentEvent) {
      gw = currentEvent.id;
    }

    const fixRes = UrlFetchApp.fetch(`https://fantasy.premierleague.com/api/fixtures/?event=${gw}`, { muteHttpExceptions: true });
    if (fixRes.getResponseCode() !== 200) {
      return `⚠️ GW${gw} fikstür verisi FPL API'den çekilemedi.`;
    }
    let fixtures = JSON.parse(fixRes.getContentText());

    if (currentEvent && gw === currentEvent.id && Array.isArray(fixtures) && fixtures.length > 0 && fixtures.every(isFixtureFinished) && nextEvent) {
      gw = nextEvent.id;
      const nextFixRes = UrlFetchApp.fetch(`https://fantasy.premierleague.com/api/fixtures/?event=${gw}`, { muteHttpExceptions: true });
      if (nextFixRes.getResponseCode() === 200) {
        fixtures = JSON.parse(nextFixRes.getContentText());
      }
    }

    const activeEvent = events.find(e => e.id === gw);
    const deadlineTime = activeEvent ? activeEvent.deadline_time : null;

    return formatMatchesReportFromRaw(fixtures, gw, teamFullNames, deadlineTime);
  } catch (e) {
    Logger.log("fetchLiveFixturesReport error: " + e);
    return `❌ Canlı fikstür çekilirken hata oluştu: ${e}`;
  }
}

function formatMatchesReportFromRaw(fixtures, gw, teamFullNames, deadlineTime) {
  if (!Array.isArray(fixtures) || fixtures.length === 0) {
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
  lines.push(`🦁 <b>PREMIER LEAGUE GW${gw} CANLI MAÇ PROGRAMI (TSİ)</b>`);

  if (deadlineTime) {
    const dlDate = new Date(deadlineTime);
    if (!isNaN(dlDate.getTime())) {
      const dlTr = new Date(dlDate.getTime() + (3 * 60 * 60 * 1000));
      const dlDayName = DAYS_TR[dlTr.getUTCDay()];
      const dlDayNum = dlTr.getUTCDate();
      const dlMonthName = MONTHS_TR[dlTr.getUTCMonth()];
      const dlHours = String(dlTr.getUTCHours()).padStart(2, '0');
      const dlMinutes = String(dlTr.getUTCMinutes()).padStart(2, '0');
      const isPast = new Date().getTime() > dlDate.getTime();
      const statusNote = isPast ? " <i>(Süre doldu)</i>" : "";
      lines.push(`⏰ <b>Son Değişiklik (Deadline):</b> ${dlDayNum} ${dlMonthName} ${dlDayName}, ${dlHours}:${dlMinutes}${statusNote}\n`);
    } else {
      lines.push("");
    }
  } else {
    lines.push("");
  }
  
  for (const [dayKey, list] of Object.entries(grouped)) {
    lines.push(`🗓️ <b>${dayKey}</b>`);
    for (const item of list) {
      const f = item.fixture;
      const hTeam = (teamFullNames && teamFullNames[f.team_h]) || (TEAM_FULL_NAMES && TEAM_FULL_NAMES[f.team_h]) || `Takım ${f.team_h}`;
      const aTeam = (teamFullNames && teamFullNames[f.team_a]) || (TEAM_FULL_NAMES && TEAM_FULL_NAMES[f.team_a]) || `Takım ${f.team_a}`;
      
      const finished = isFixtureFinished(f);
      if (finished && f.team_h_score !== null && f.team_h_score !== undefined && f.team_a_score !== null && f.team_a_score !== undefined) {
        lines.push(`• <b>${item.time}</b> ➔ ${hTeam} <b>${f.team_h_score} - ${f.team_a_score}</b> ${aTeam} (Bitti)`);
      } else if (f.started && f.team_h_score !== null && f.team_h_score !== undefined && f.team_a_score !== null && f.team_a_score !== undefined) {
        lines.push(`• <b>${item.time}</b> ➔ ${hTeam} <b>${f.team_h_score} - ${f.team_a_score}</b> ${aTeam} (🔴 Canlı)`);
      } else {
        lines.push(`• <b>${item.time}</b> ➔ <b>${hTeam}</b> vs <b>${aTeam}</b>`);
      }
    }
    lines.push("");
  }
  
  lines.push("⏰ <i>Tüm başlama saatleri Türkiye saati (TSİ / GMT+3) ile canlı güncellenmektedir.</i>");
  return lines.join("\n");
}
