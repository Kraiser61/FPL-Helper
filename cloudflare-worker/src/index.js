// ============================================================================
// 🦁 FPL HELPER - CLOUDFLARE WORKER TELEGRAM BOT WEBHOOK ROUTER
// ============================================================================
// Google Apps Script yerine %100 otomatik, sıfır bekleme süreli Cloudflare Edge Router.

const DEFAULT_BOT_TOKEN = "8315284284:AAF4HjtfP1kW5rNUPRe5n1J1KBg4PsT83Jg";
const DEFAULT_GITHUB_REPO = "Kraiser61/FPL-Helper";

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

let cachedConfig = null;
let cachedConfigExpiry = 0;
let cachedBootstrap = null;
let cachedBootstrapExpiry = 0;

async function fetchBotConfig(githubRepo) {
  const now = Date.now();
  if (cachedConfig && now < cachedConfigExpiry) {
    return cachedConfig;
  }
  try {
    const url = `https://raw.githubusercontent.com/${githubRepo}/main/data/bot_config.json?t=${now}`;
    const res = await fetch(url, { headers: { "User-Agent": "Cloudflare-Worker-Telegram-Bot" } });
    if (res.ok) {
      const cfg = await res.json();
      cachedConfig = cfg;
      cachedConfigExpiry = now + 60000; // 60 saniye önbellek
      return cfg;
    }
  } catch (e) {
    console.error("fetchBotConfig error:", e);
  }
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

async function fetchBootstrapStatic() {
  const now = Date.now();
  if (cachedBootstrap && now < cachedBootstrapExpiry) {
    return cachedBootstrap;
  }
  try {
    const res = await fetch("https://fantasy.premierleague.com/api/bootstrap-static/", {
      headers: { "User-Agent": "FPL-Telegram-Bot" }
    });
    if (res.ok) {
      const data = await res.json();
      cachedBootstrap = data;
      cachedBootstrapExpiry = now + 300000; // 5 dakika önbellek
      return data;
    }
  } catch (e) {
    console.error("fetchBootstrapStatic error:", e);
  }
  return null;
}

async function sendTelegramMessage(botToken, chatId, text) {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  const payload = {
    chat_id: chatId,
    text: text,
    parse_mode: "HTML"
  };
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    console.error("sendTelegramMessage error:", err);
  }
}

async function triggerGitHubActions(githubRepo, githubPat, teamDataText, chatId, botToken) {
  if (!githubPat || githubPat.length < 10) {
    if (chatId) {
      await sendTelegramMessage(botToken, chatId, "⚠️ <b>Hata:</b> Cloudflare Worker içinde GITHUB_PAT (GitHub Token) tanımlı değil.");
    }
    return null;
  }
  const url = `https://api.github.com/repos/${githubRepo}/dispatches`;
  const payload = {
    event_type: "telegram-trigger",
    client_payload: {
      team_data: teamDataText,
      chat_id: String(chatId || "")
    }
  };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${githubPat}`,
        "Accept": "application/vnd.github+json",
        "User-Agent": "Cloudflare-Worker-Telegram-Bridge",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    const code = res.status;
    if (code !== 204 && chatId) {
      const errText = await res.text();
      await sendTelegramMessage(botToken, chatId, `⚠️ <b>GitHub Tetikleme Hatası (${code}):</b> ${errText || 'GitHub yetkisi reddedildi.'}`);
    }
    return res;
  } catch (err) {
    console.error("triggerGitHubActions error:", err);
    if (chatId) {
      await sendTelegramMessage(botToken, chatId, `❌ <b>GitHub Bağlantı Hatası:</b> ${err.message}`);
    }
  }
}

async function fetchAnalysisJson(githubRepo) {
  try {
    const rawUrl = `https://raw.githubusercontent.com/${githubRepo}/main/data/fpl_analysis.json?t=${Date.now()}`;
    const res = await fetch(rawUrl, { headers: { "User-Agent": "Cloudflare-Worker-Telegram-Bot" } });
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.error("fetchAnalysisJson error:", e);
  }
  return null;
}

function isAnalysisFresh(data, maxHours = 2) {
  if (!data || !data.meta) return false;
  let genTime = null;
  if (data.meta.generated_at_epoch) {
    genTime = data.meta.generated_at_epoch * 1000;
  } else if (data.meta.generated_at_iso) {
    genTime = new Date(data.meta.generated_at_iso).getTime();
  } else if (data.meta.generated_at) {
    const s = String(data.meta.generated_at).replace(" ", "T");
    genTime = new Date(s).getTime();
  }
  if (!genTime || isNaN(genTime)) return false;
  const now = Date.now();
  const diffHours = (now - genTime) / (1000 * 60 * 60);
  return diffHours <= maxHours;
}

function getStaleDataMessage(data, config) {
  let timeText = "2 saatten önce";
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
    "🔹 <b>/kadro</b> (veya <b>/kadrom</b>) ➔ Kayıtlı 15 kişilik kadronuzu mevki mevki, anlık değer ve takımlarıyla listeler.",
    "🔹 <b>/yeni [15 Oyuncu]</b> ➔ 15 kişilik yeni kadronuzu sıfırdan kaydeder (Örn: <code>/yeni Raya, Gabriel, Saka, Haaland...</code>).",
    "🔹 <b>/ft [0-5]</b> ➔ Serbest transfer (FT) hakkınızı günceller / görüntüler.",
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

async function fetchSquadReport(githubRepo) {
  try {
    const rawUrl = `https://raw.githubusercontent.com/${githubRepo}/main/data/synced_team.json?t=${Date.now()}`;
    const syncRes = await fetch(rawUrl, { headers: { "User-Agent": "Cloudflare-Worker-Telegram-Bot" } });
    if (!syncRes.ok) {
      return "⚠️ Kayıtlı bir kadro bulunamadı. Lütfen önce <b>/kadro [15 oyuncu]</b> veya <b>/analiz</b> komutunu çalıştırın.";
    }
    const synced = await syncRes.json();
    const picks = (synced && synced.team_data && Array.isArray(synced.team_data.picks)) ? synced.team_data.picks : [];
    if (picks.length === 0) {
      return "⚠️ Kayıtlı kadronuzda oyuncu bulunamadı.";
    }

    const bootstrap = await fetchBootstrapStatic();
    const elements = (bootstrap && Array.isArray(bootstrap.elements)) ? bootstrap.elements : [];
    const elMap = {};
    for (const el of elements) {
      elMap[el.id] = el;
    }

    const gks = [];
    const defs = [];
    const mids = [];
    const fwds = [];
    let totalCost = 0;

    for (const p of picks) {
      const el = elMap[p.element];
      if (!el) continue;

      const pName = el.web_name || el.first_name + " " + el.second_name;
      const tCode = TEAM_NAMES[el.team] || `TAK${el.team}`;
      const price = el.now_cost ? (el.now_cost / 10.0) : 0;
      totalCost += price;

      const priceStr = `£${price.toFixed(1)}m`;
      const line = `• <b>${pName}</b> (${tCode}) ➔ <b>${priceStr}</b>`;

      if (el.element_type === 1) gks.push(line);
      else if (el.element_type === 2) defs.push(line);
      else if (el.element_type === 3) mids.push(line);
      else if (el.element_type === 4) fwds.push(line);
    }

    const bank = (synced.team_data && synced.team_data.transfers && typeof synced.team_data.transfers.bank === "number")
      ? (synced.team_data.transfers.bank / 10.0).toFixed(1)
      : "0.0";
    const ftCount = (synced.team_data && synced.team_data.transfers && typeof synced.team_data.transfers.limit === "number")
      ? synced.team_data.transfers.limit
      : 1;

    const lines = [
      "📋 <b>MEVCUT 15 KİŞİLİK KADRONUZ</b>\n",
      "🧤 <b>Kaleciler (GK):</b>",
      ...(gks.length ? gks : ["• <i>Veri yok</i>"]),
      "",
      "🛡️ <b>Defanslar (DEF):</b>",
      ...(defs.length ? defs : ["• <i>Veri yok</i>"]),
      "",
      "⚙️ <b>Orta Sahalar (MID):</b>",
      ...(mids.length ? mids : ["• <i>Veri yok</i>"]),
      "",
      "⚡ <b>Forvetler (FWD):</b>",
      ...(fwds.length ? fwds : ["• <i>Veri yok</i>"]),
      "",
      `💰 <b>Kadro Değeri:</b> £${totalCost.toFixed(1)}m | <b>Banka:</b> £${bank}m`,
      `🎟️ <b>Serbest Transfer:</b> ${ftCount} FT`
    ];

    return lines.join("\n");
  } catch (err) {
    console.error("fetchSquadReport error:", err);
    return `❌ Kadro çekilirken hata oluştu: ${err.message}`;
  }
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
    const ko = new Date(f.kickoff_time);
    const now = new Date();
    if ((now.getTime() - ko.getTime()) > (110 * 60 * 1000)) return true;
  }
  return false;
}

async function fetchLiveFixturesReport() {
  try {
    const bootstrap = await fetchBootstrapStatic();
    if (!bootstrap) {
      return "⚠️ FPL API'ye erişilemedi. Lütfen birazdan tekrar deneyin.";
    }
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

    const fixRes = await fetch(`https://fantasy.premierleague.com/api/fixtures/?event=${gw}`, {
      headers: { "User-Agent": "FPL-Telegram-Bot" }
    });
    if (!fixRes.ok) {
      return `⚠️ GW${gw} fikstür verisi FPL API'den çekilemedi.`;
    }
    let fixtures = await fixRes.json();

    if (currentEvent && gw === currentEvent.id && Array.isArray(fixtures) && fixtures.length > 0 && fixtures.every(isFixtureFinished) && nextEvent) {
      gw = nextEvent.id;
      const nextFixRes = await fetch(`https://fantasy.premierleague.com/api/fixtures/?event=${gw}`, {
        headers: { "User-Agent": "FPL-Telegram-Bot" }
      });
      if (nextFixRes.ok) {
        fixtures = await nextFixRes.json();
      }
    }

    return formatMatchesReportFromRaw(fixtures, gw, teamFullNames);
  } catch (e) {
    console.error("fetchLiveFixturesReport error:", e);
    return `❌ Canlı fikstür çekilirken hata oluştu: ${e.message}`;
  }
}

function formatMatchesReportFromRaw(fixtures, gw, teamFullNames) {
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
  lines.push(`🦁 <b>PREMIER LEAGUE GW${gw} CANLI MAÇ PROGRAMI (TSİ)</b>\n`);
  
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

async function handleTelegramWebhook(request, env, ctx) {
  try {
    const update = await request.json();
    if (!update.message || !update.message.text) {
      return new Response("OK", { status: 200 });
    }

    const botToken = env.BOT_TOKEN || DEFAULT_BOT_TOKEN;
    const githubRepo = env.GITHUB_REPO || DEFAULT_GITHUB_REPO;
    const githubPat = env.GITHUB_PAT || "";

    const chatId = update.message.chat.id;
    const text = update.message.text.trim();
    const textLower = text.toLowerCase();
    const cleanCmd = textLower.replace(/^\//, "").trim();

    const config = await fetchBotConfig(githubRepo);
    const wm = (config && config.wait_messages) ? config.wait_messages : {};

    // 1. KADRO LİSTELEME KOMUTLARI (⚡ Anında Cloudflare üzerinden yanıt verir)
    const squadListCmds = [
      "kadro", "kadrom", "/kadro", "/kadrom",
      "takim", "takım", "takimim", "takımım", "kadromuz",
      "15", "oyuncular", "kadromu göster", "kadromu goster", "kadro listesi", "mevcut kadro", "mevcut kadrom"
    ];
    if (squadListCmds.includes(cleanCmd) || squadListCmds.includes(textLower)) {
      ctx.waitUntil((async () => {
        const rep = await fetchSquadReport(githubRepo);
        await sendTelegramMessage(botToken, chatId, rep);
      })());
      return new Response("OK", { status: 200 });
    }

    // 2. YENİ KADRO TANIMLAMA YARDIMI (Oyuncu listesi verilmemişse rehber mesajı döner)
    if (cleanCmd === "yeni" || textLower === "yeni" || textLower === "/yeni") {
      const guideMsg = "ℹ️ <b>15 Kişilik Yeni Kadro Tanımlama:</b>\n\nLütfen 15 oyuncu ismini aralarında virgül bırakarak yazın.\n\n<b>Örnek Kullanım:</b>\n<code>/yeni Raya, Leno, Gabriel, Saliba, Robinson, Konsa, Greaves, Salah, Palmer, Saka, Rogers, Winks, Haaland, Wood, Stewart</code>";
      ctx.waitUntil(sendTelegramMessage(botToken, chatId, guideMsg));
      return new Response("OK", { status: 200 });
    }

    // 3. AĞIR MOTOR & ÇÖZÜCÜ KOMUTLARI (GitHub Actions Tetikler + Anında Geri Bildirim)
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
            else if (/yeni|kadro/i.test(text)) actionWaitKey = "yeni";
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
        textLower.startsWith("/yeni ") || textLower.startsWith("yeni ") ||
        textLower.startsWith("/kadro ") || textLower.startsWith("kadro ") ||
        cleanCmd === "analiz" || cleanCmd === "taktik"
      ) {
        isActionCommand = true;
        if (cleanCmd === "optimal" || cleanCmd === "ruyatimi" || cleanCmd === "rüya takım" || cleanCmd === "ruya takim" || cleanCmd === "wildcard") actionWaitKey = "optimal";
        else if (textLower.startsWith("/transfer") || textLower.startsWith("transfer") || textLower.includes("yerine")) actionWaitKey = "transfer";
        else if (textLower.startsWith("/ft") || textLower.startsWith("ft") || textLower.startsWith("/hak") || textLower.startsWith("hak")) actionWaitKey = "ft";
        else if (textLower.startsWith("/yeni ") || textLower.startsWith("yeni ") || textLower.startsWith("/kadro ") || textLower.startsWith("kadro ")) actionWaitKey = "yeni";
        else if (textLower.includes("rüya takım ile değiştir") || textLower.includes("kadroyu optimal")) actionWaitKey = "adopt_dream_team";
      }
    }

    if (isActionCommand) {
      const waitMsg = wm[actionWaitKey] || wm.analiz || "🧠 <b>Strateji analizi başlatıldı...</b>";
      ctx.waitUntil((async () => {
        await sendTelegramMessage(botToken, chatId, waitMsg);
        await triggerGitHubActions(githubRepo, githubPat, text, chatId, botToken);
      })());
      return new Response("OK", { status: 200 });
    }

    // 3. YARDIM / KOMUT REHBERİ
    if (cleanCmd === "yardim" || cleanCmd === "help" || cleanCmd === "yardım" || cleanCmd === "komutlar") {
      const helpMsg = (config && config.help_text) ? config.help_text : getHelpText();
      ctx.waitUntil(sendTelegramMessage(botToken, chatId, helpMsg));
      return new Response("OK", { status: 200 });
    }

    // 4. CANLI FİKSTÜR VE MAÇ PROGRAMI
    const matchCommands = [
      "maclar", "maçlar", "fikstur", "fikstür", "program", "maç programı", "mac programi", "haftanın maçları", "haftanin maclari", "/haftalikmaclar"
    ];
    if (matchCommands.includes(cleanCmd) || matchCommands.includes(textLower)) {
      ctx.waitUntil((async () => {
        const report = await fetchLiveFixturesReport();
        await sendTelegramMessage(botToken, chatId, report);
      })());
      return new Response("OK", { status: 200 });
    }

    // 5. STRATEJİ VE ÖNBELLEK RAPORLARI
    const instantCommands = [
      "kaptan", "captain", "c kim", "kime verelim",
      "sakatlar", "revir", "saglik", "sağlık", "injury",
      "salincak", "salıncak", "swings", "kolayfikstur", "kolayfikstür", "kolay maçlar", "kolay fikstür",
      "fiyat", "price", "zam", "düşüş", "fiyatlar"
    ];

    const isInstantCmd = instantCommands.includes(cleanCmd) || instantCommands.includes(textLower);

    if (isInstantCmd) {
      ctx.waitUntil((async () => {
        const data = await fetchAnalysisJson(githubRepo);
        if (!data) {
          await sendTelegramMessage(botToken, chatId, "⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.");
          return;
        }

        if (!isAnalysisFresh(data, 2)) {
          await sendTelegramMessage(botToken, chatId, getStaleDataMessage(data, config));
          return;
        }

        if (data.reports && typeof data.reports === "object") {
          if (data.reports[cleanCmd]) {
            await sendTelegramMessage(botToken, chatId, data.reports[cleanCmd]);
            return;
          }
          
          const aliasMap = {
            "c kim": "kaptan", "captain": "kaptan", "kime verelim": "kaptan",
            "revir": "sakatlar", "saglik": "sakatlar", "sağlık": "sakatlar", "injury": "sakatlar",
            "kolay maçlar": "salincak", "kolay fikstür": "salincak", "swings": "salincak", "kolayfikstur": "salincak", "kolayfikstür": "salincak",
            "fiyatlar": "fiyat", "price": "fiyat", "zam": "fiyat", "düşüş": "fiyat"
          };
          const mappedKey = aliasMap[cleanCmd] || aliasMap[textLower];
          if (mappedKey && data.reports[mappedKey]) {
            await sendTelegramMessage(botToken, chatId, data.reports[mappedKey]);
            return;
          }
        }

        if (cleanCmd === "kaptan") {
          await sendTelegramMessage(botToken, chatId, formatCaptainReport(data));
          return;
        }
        if (cleanCmd === "sakatlar" || cleanCmd === "revir") {
          await sendTelegramMessage(botToken, chatId, formatHealthReport(data));
          return;
        }
        if (cleanCmd === "salincak") {
          await sendTelegramMessage(botToken, chatId, formatFixtureReport(data));
          return;
        }
        if (cleanCmd === "fiyat") {
          await sendTelegramMessage(botToken, chatId, formatPriceReport(data));
          return;
        }
      })());
      return new Response("OK", { status: 200 });
    }

    // 6. TANINMAYAN KOMUT
    const unrecMsg = (config && config.unrecognized_command) ? config.unrecognized_command : "🤖 <b>Komut anlaşılamadı.</b> Mevcut komutlar için <b>/yardim</b> yazabilirsiniz.";
    ctx.waitUntil(sendTelegramMessage(botToken, chatId, unrecMsg));
    return new Response("OK", { status: 200 });

  } catch (err) {
    console.error("handleTelegramWebhook error:", err);
    return new Response("OK", { status: 200 });
  }
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "GET") {
      return new Response("🦁 FPL Helper Cloudflare Webhook is running!", {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" }
      });
    }
    if (request.method === "POST") {
      return await handleTelegramWebhook(request, env, ctx);
    }
    return new Response("Method Not Allowed", { status: 405 });
  }
};
