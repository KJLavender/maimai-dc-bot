const fs = require('fs');
const { Client, Events, GatewayIntentBits, REST, Routes, SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, ComponentType, MessageFlags, AttachmentBuilder } = require('discord.js');
const { spawn } = require('child_process');
require('dotenv').config();

const token = process.env.MAI_BOT_TOKEN;
const clientId = process.env.CLIENT_ID;
const guildId = process.env.GUILD_ID;
const BINDINGS_FILE = 'bindings.json';

// --- 綁定資料管理 ---
function loadBindings() {
    if (!fs.existsSync(BINDINGS_FILE)) return {};
    try {
        return JSON.parse(fs.readFileSync(BINDINGS_FILE, 'utf-8'));
    } catch { return {}; }
}

function saveBindings(data) {
    fs.writeFileSync(BINDINGS_FILE, JSON.stringify(data, null, 2), 'utf-8');
}

// --- Python 子程序 ---
function runPython(script, args) {
    return new Promise((resolve) => {
        const proc = spawn('python3', [script, ...args], {
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });
        let stdout = '';
        let stderr = '';
        proc.stdout.setEncoding('utf8');
        proc.stderr.setEncoding('utf8');
        proc.stdout.on('data', (d) => { stdout += d; });
        proc.stderr.on('data', (d) => { stderr += d; });
        proc.on('error', (err) => resolve({ code: -1, stdout, stderr: stderr + err.message }));
        proc.on('close', (code) => resolve({ code, stdout, stderr }));
    });
}

function parseJson(text) {
    try { return JSON.parse(text.trim()); } catch { return null; }
}

// Selenium 的 stacktrace 很長，只留最後幾行有用的
function tailLog(text, lines = 15) {
    return text.trim().split('\n').filter(l => !/^#\d+ 0x/.test(l)).slice(-lines).join('\n');
}

const SITE_DOWN_PATTERN = /ERR_CONNECTION_REFUSED|ERR_CONNECTION_TIMED_OUT|ERR_CONNECTION_RESET|ERR_NAME_NOT_RESOLVED|ERR_TIMED_OUT|ERR_INTERNET_DISCONNECTED/;
const SITE_DOWN_MESSAGE = '❌ maimai 官網目前無法連線（可能正在維護），請稍後再試。';

// --- 歌曲顯示 ---
const COVER_BASE = 'https://dp4p6x0xfi5o9.cloudfront.net/maimai/img/cover/';
const DIFF_LABEL = { basic: 'BASIC', advanced: 'ADVANCED', expert: 'EXPERT', master: 'MASTER', remaster: 'Re:MASTER' };

function sheetLabel(sheet) {
    const type = sheet.type === 'dx' ? 'DX' : 'STD';
    return `[${type}] ${DIFF_LABEL[sheet.difficulty] || String(sheet.difficulty).toUpperCase()} ${sheet.level}`;
}

function buildSongEmbed(song, title = `🎵 ${song.title}`) {
    const lines = song.sheets.map((s) => {
        const designer = s.designer && s.designer !== '-' ? ` — ${s.designer}` : '';
        return `${sheetLabel(s)}｜定數 **${s.const ?? '未知'}**${designer}`;
    });
    const embed = new EmbedBuilder()
        .setTitle(title.substring(0, 256))
        .setColor(0xFFD700)
        .addFields(
            { name: '藝術家', value: song.artist || '未知', inline: true },
            { name: 'BPM', value: String(song.bpm ?? '未知'), inline: true },
            { name: '版本', value: song.version || '未知', inline: true },
            { name: '📊 譜面定數', value: lines.join('\n').substring(0, 1024) || '無資料' }
        );
    return embed;
}

// Discord 代理抓不到 CloudFront 封面（寬高會是 0），改成自己下載後當附件上傳
async function coverAttachment(song) {
    if (!song.image) return null;
    try {
        const res = await fetch(COVER_BASE + encodeURIComponent(song.image), { signal: AbortSignal.timeout(5000) });
        if (!res.ok) return null;
        return new AttachmentBuilder(Buffer.from(await res.arrayBuffer()), { name: 'cover.png' });
    } catch {
        return null;
    }
}

async function withCover(embed, song) {
    const cover = await coverAttachment(song);
    if (cover) embed.setThumbnail('attachment://cover.png');
    return { embeds: [embed], files: cover ? [cover] : [] };
}

async function songMessage(song, title, description) {
    const embed = buildSongEmbed(song, title);
    if (description) embed.setDescription(description);
    return withCover(embed, song);
}

// --- Rating 計算：floor(定數 × 達成率(上限 100.5%) × 評級係數) ---
const RANKS = [
    { name: 'SSS+', ach: 100.5, k: 22.4 },
    { name: 'SSS', ach: 100.0, k: 21.6 },
    { name: 'SS+', ach: 99.5, k: 21.1 },
    { name: 'SS', ach: 99.0, k: 20.8 },
    { name: 'S+', ach: 98.0, k: 20.3 },
    { name: 'S', ach: 97.0, k: 20.0 },
    { name: 'AAA', ach: 94.0, k: 16.8 },
];

// 用整數運算避免浮點誤差（例如 299.999... 被捨去）
function chartRating(constant, rank) {
    const c10 = Math.round(Number(constant) * 10);
    const ach = Math.round(rank.ach * 10000);
    const k10 = Math.round(rank.k * 10);
    return Math.floor((c10 * ach * k10) / 1e8);
}

function calcConstEmbed(constant) {
    const lines = RANKS.map(r => `**${r.name}**（${r.ach.toFixed(1)}%）→ **${chartRating(constant, r)}**`);
    return new EmbedBuilder()
        .setTitle(`📐 定數 ${constant.toFixed(1)}`)
        .setDescription(lines.join('\n'))
        .setColor(0xE67E22);
}

function calcSongMessage(song) {
    const sheets = song.sheets.filter(s => s.const);
    const embed = new EmbedBuilder()
        .setTitle(`📐 ${song.title}`.substring(0, 256))
        .setColor(0xE67E22);
    if (sheets.length === 0) {
        embed.setDescription('這首歌目前沒有定數資料。');
    } else {
        embed.addFields(sheets.map(s => ({
            name: `${sheetLabel(s)}｜定數 ${s.const}`,
            value: RANKS.slice(0, 6).map(r => `${r.name} **${chartRating(s.const, r)}**`).join('・'),
        })));
    }
    return withCover(embed, song);
}

function rangeText(low, high) {
    return low === high ? `${low}` : `${Math.min(low, high)} ~ ${Math.max(low, high)}`;
}

// --- 歌曲查詢指令 (不需要全域鎖) ---
async function handleSearch(interaction, render = songMessage) {
    const query = interaction.options.getString('query');
    const { code, stdout, stderr } = await runPython('search_song.py', [query]);
    const data = parseJson(stdout);
    if (code !== 0 || !data || data.error) {
        if (code !== 0) console.error(`search_song.py 失敗 (Code ${code}):\n${tailLog(stderr)}`);
        return interaction.editReply(`❌ 找不到與「${query}」相關的歌曲。`);
    }

    const results = data.results;
    if (results.length === 1) {
        return interaction.editReply(await render(results[0]));
    }

    const embed = new EmbedBuilder()
        .setTitle(`🔍 搜尋「${query}」的結果`.substring(0, 256))
        .setDescription(results.map((s, i) => `**${i + 1}.** ${s.title} — ${s.artist}`).join('\n'))
        .setColor(0x3498DB)
        .setFooter({ text: '請點擊下方按鈕選擇歌曲' });

    const row = new ActionRowBuilder().addComponents(
        results.map((song, i) => new ButtonBuilder()
            .setCustomId(`song_${i}`)
            .setLabel(`${i + 1}. ${song.title}`.substring(0, 80))
            .setStyle(ButtonStyle.Primary))
    );

    const response = await interaction.editReply({ embeds: [embed], components: [row] });
    const collector = response.createMessageComponentCollector({ componentType: ComponentType.Button, time: 60000 });

    collector.on('collect', async (btn) => {
        const song = results[Number(btn.customId.split('_')[1])];
        if (!song) return;
        try {
            if (btn.user.id === interaction.user.id) {
                collector.stop('selected');
                await btn.deferUpdate();
                await btn.editReply({ ...(await render(song)), components: [] });
            } else {
                await btn.deferReply({ flags: MessageFlags.Ephemeral });
                await btn.editReply(await render(song));
            }
        } catch (e) { console.error('選歌回應失敗:', e.message); }
    });

    collector.on('end', (_, reason) => {
        if (reason !== 'selected') interaction.editReply({ components: [] }).catch(() => {});
    });
}

async function handleConst(interaction) {
    const low = interaction.options.getNumber('lv');
    const high = interaction.options.getNumber('to') ?? low;
    const { code, stdout, stderr } = await runPython('search_song.py', ['--const', String(low), String(high)]);
    const data = parseJson(stdout);
    if (code !== 0 || !data || data.error) {
        if (code !== 0) console.error(`search_song.py --const 失敗 (Code ${code}):\n${tailLog(stderr)}`);
        return interaction.editReply(`❌ 找不到定數 ${rangeText(low, high)} 的譜面。`);
    }

    const lines = [];
    let length = 0;
    for (const item of data.items) {
        const line = `\`${item.const}\` ${sheetLabel(item)} - ${item.title}`;
        if (length + line.length + 1 > 4000) break;
        lines.push(line);
        length += line.length + 1;
    }

    const footer = lines.length < data.total ? `共 ${data.total} 個譜面，只顯示前 ${lines.length} 個` : `共 ${data.total} 個譜面`;
    const embed = new EmbedBuilder()
        .setTitle(`📊 定數 ${rangeText(low, high)}`)
        .setDescription(lines.join('\n'))
        .setColor(0x9B59B6)
        .setFooter({ text: footer });
    return interaction.editReply({ embeds: [embed] });
}

async function handleRandom(interaction) {
    const lv = interaction.options.getNumber('lv');
    const to = interaction.options.getNumber('to');
    const low = lv ?? 1;
    const high = to ?? lv ?? 15;
    const { code, stdout, stderr } = await runPython('search_song.py', ['--random', String(low), String(high)]);
    const data = parseJson(stdout);
    if (code !== 0 || !data || data.error) {
        if (code !== 0) console.error(`search_song.py --random 失敗 (Code ${code}):\n${tailLog(stderr)}`);
        return interaction.editReply(`❌ 找不到定數 ${rangeText(low, high)} 的譜面。`);
    }

    return interaction.editReply(await songMessage(
        data.song,
        `🎲 ${data.song.title}`,
        `🎯 **${sheetLabel(data.pick)}｜定數 ${data.pick.const}**`
    ));
}

async function handleCalc(interaction) {
    const query = interaction.options.getString('query').trim();
    const constant = Number(query);
    if (/^\d{1,2}(\.\d)?$/.test(query) && constant >= 1 && constant <= 15) {
        return interaction.editReply({ embeds: [calcConstEmbed(constant)] });
    }
    return handleSearch(interaction, calcSongMessage);
}

const SONG_COMMANDS = { m: handleSearch, c: handleConst, r: handleRandom, calc: handleCalc };

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildMembers,
    ]
});

// --- 全域鎖變數 ---
let isProcessing = false;

const commands = [
    new SlashCommandBuilder()
        .setName('b50')
        .setDescription('查詢你的 B50 資料 (需先 /bind 綁定)'),
    new SlashCommandBuilder()
        .setName('addfriend')
        .setDescription('讓機器人主動加你好友')
        .addStringOption(option =>
            option.setName('friendcode').setDescription('請輸入你的好友代碼 (Friend Code)').setRequired(true)
        ),
    new SlashCommandBuilder()
        .setName('m')
        .setDescription('查詢歌曲定數')
        .addStringOption(option =>
            option.setName('query').setDescription('請輸入歌名關鍵字').setRequired(true)
        ),
    new SlashCommandBuilder()
        .setName('c')
        .setDescription('依定數列出譜面（例：/c 13.1 或 /c 13.0 13.4）')
        .addNumberOption(option =>
            option.setName('lv').setDescription('定數（或範圍下限）').setRequired(true).setMinValue(1).setMaxValue(15)
        )
        .addNumberOption(option =>
            option.setName('to').setDescription('範圍上限（選填）').setMinValue(1).setMaxValue(15)
        ),
    new SlashCommandBuilder()
        .setName('r')
        .setDescription('依定數隨機抽一首（例：/r 13.5 或 /r 13.5 14.0）')
        .addNumberOption(option =>
            option.setName('lv').setDescription('定數（或範圍下限），不填就全部隨機').setMinValue(1).setMaxValue(15)
        )
        .addNumberOption(option =>
            option.setName('to').setDescription('範圍上限（選填）').setMinValue(1).setMaxValue(15)
        ),
    new SlashCommandBuilder()
        .setName('bind')
        .setDescription('綁定你的 maimai 好友ID到 Discord 帳號')
        .addStringOption(option =>
            option.setName('friendid').setDescription('你的 maimai 好友ID (Friend ID)').setRequired(true)
        ),
    new SlashCommandBuilder()
        .setName('unbind')
        .setDescription('解除你的 maimai 好友ID 綁定'),
    new SlashCommandBuilder()
        .setName('myid')
        .setDescription('查看你目前綁定的 maimai 好友ID'),
    new SlashCommandBuilder()
        .setName('calc')
        .setDescription('算 rating：輸入定數（例：13.3）或歌名')
        .addStringOption(option =>
            option.setName('query').setDescription('定數或歌名').setRequired(true)
        ),
    new SlashCommandBuilder()
        .setName('h')
        .setDescription('顯示所有指令與說明')
].map(command => command.toJSON());

const HELP_TEXT = [
    '**🎵 查歌**',
    '`/m 歌名` — 查歌曲定數，打部分歌名就可以；多首符合時點按鈕選',
    '`/c 13.1` — 列出定數 13.1 的譜面；`/c 13.0 13.4` 列出範圍內的譜面',
    '`/r` — 隨機抽一個譜面；`/r 13.5` 指定定數、`/r 13.5 14.0` 指定範圍',
    '`/calc 13.3` — 算定數 13.3 各評級的 rating；`/calc 歌名` 算那首歌各難度的 rating',
    '',
    '**📈 B50**',
    '`/bind 好友ID` — 綁定你的 maimai 好友 ID（用 /b50 前要先綁定）',
    '`/b50` — 產生你的 Best 50 圖片（機器人需是你的遊戲好友）',
    '`/addfriend 好友代碼` — 讓機器人送好友申請給你',
    '`/myid` — 查看目前綁定的好友 ID',
    '`/unbind` — 解除綁定',
    '',
    '`/h` — 顯示這個說明',
].join('\n');

const rest = new REST({ version: '10' }).setToken(token);

client.once(Events.ClientReady, async (readyClient) => {
    console.log(`✅ Ready! Logged in as ${readyClient.user.tag}`);
    try {
        await rest.put(Routes.applicationGuildCommands(clientId, guildId), { body: commands });
        console.log('成功註冊指令：/b50, /addfriend, /m, /c, /r, /calc, /bind, /unbind, /myid, /h');
    } catch (error) {
        console.error('註冊指令失敗:', error);
    }
});

client.on(Events.InteractionCreate, async (interaction) => {
    if (!interaction.isChatInputCommand()) return;

    const { commandName } = interaction;

    // --- 快速指令 (不需要全域鎖) ---
    if (commandName === 'bind') {
        const friendId = interaction.options.getString('friendid');
        const bindings = loadBindings();
        bindings[interaction.user.id] = friendId;
        saveBindings(bindings);
        return interaction.reply({ content: `✅ 綁定成功！你的 Discord 帳號已綁定 Friend ID: \`${friendId}\`\n下次使用 /b50 可以不用再輸入 ID 了！`, ephemeral: true });
    }

    if (commandName === 'unbind') {
        const bindings = loadBindings();
        if (bindings[interaction.user.id]) {
            delete bindings[interaction.user.id];
            saveBindings(bindings);
            return interaction.reply({ content: '✅ 已解除綁定。', ephemeral: true });
        }
        return interaction.reply({ content: '⚠️ 你目前沒有綁定任何 Friend ID。', ephemeral: true });
    }

    if (commandName === 'myid') {
        const bindings = loadBindings();
        const boundId = bindings[interaction.user.id];
        if (boundId) {
            return interaction.reply({ content: `🎮 你目前綁定的 Friend ID: \`${boundId}\``, ephemeral: true });
        }
        return interaction.reply({ content: '⚠️ 你尚未綁定 Friend ID，請使用 `/bind` 指令綁定。', ephemeral: true });
    }

    if (commandName === 'h') {
        const embed = new EmbedBuilder()
            .setTitle('📖 指令說明')
            .setDescription(HELP_TEXT)
            .setColor(0x2ECC71);
        return interaction.reply({ embeds: [embed] });
    }

    if (SONG_COMMANDS[commandName]) {
        try {
            await interaction.deferReply();
        } catch (err) {
            console.error("❌ DeferReply 失敗，互動已過期 (超過 3 秒):", err.message);
            return;
        }
        try {
            await SONG_COMMANDS[commandName](interaction);
        } catch (e) { console.error(`/${commandName} 回應失敗:`, e.message); }
        return;
    }

    // --- 檢查全域鎖 ---
    if (isProcessing) {
        return interaction.reply({ content: "⚠️ 機器人正在處理另一個請求中，請稍候 30-60 秒再試。", ephemeral: true });
    }

    let deferred = false;
    try {
        await interaction.deferReply();
        deferred = true;
    } catch (err) {
        console.error("❌ DeferReply 失敗，互動已過期 (超過 3 秒):", err.message);
        return;
    }
    
    // 進入指令邏輯，上鎖
    isProcessing = true;

    // --- 指令 A: b50 ---
    if (commandName === 'b50') {
        const bindings = loadBindings();
        const TARGET_FRIEND_ID = bindings[interaction.user.id];
        if (!TARGET_FRIEND_ID) {
            isProcessing = false;
            return interaction.editReply('❌ 你尚未綁定 Friend ID，請先使用 `/bind <你的ID>` 綁定。');
        }

        const pythonProcess = spawn('python3', ['catch-friend-score.py', TARGET_FRIEND_ID], {
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });

        let resultData = "";
        let errorData = "";

        pythonProcess.stderr.on('data', (data) => {
            errorData += data.toString();
        });

        pythonProcess.stdout.on('data', (data) => {
            const output = data.toString();
            resultData += output;
            const lines = output.split('\n').filter(l => l.trim().length > 0);
            lines.forEach((line) => {
                if (!line.includes("OUTPUT_FILE:")) {
                    interaction.editReply(`⏳ **正在分析**：${line.trim()}`).catch(() => {});
                }
            });
        });

        pythonProcess.on('close', async (code) => {
            isProcessing = false; // 程序結束，解鎖
            if (!deferred) return;
            try {
                if (code === 0) {
                    const fileMatch = resultData.match(/OUTPUT_FILE:(.+)/);
                    if (fileMatch && fileMatch[1].trim() !== "ERROR_PATH") {
                        const filePath = fileMatch[1].trim();

                        // 1. 先上傳到 Discord
                        await interaction.editReply({
                            content: `✅ **${TARGET_FRIEND_ID}** 的 B50 分析完成！`,
                            files: [filePath]
                        });

                        // 2. 上傳完畢後立刻刪除檔案
                        if (fs.existsSync(filePath)) {
                            fs.unlinkSync(filePath);
                            console.log(`🗑️ 已刪除暫存圖檔: ${filePath}`);
                        }
                    } else {
                        await interaction.editReply(`❌ 分析完成，但找不到數據。請確認是否已加好友。`);
                    }
                } else {
                    console.error(`catch-friend-score.py 失敗 (Code ${code}):\n${tailLog(errorData)}`);
                    if (SITE_DOWN_PATTERN.test(errorData + resultData)) {
                        await interaction.editReply(SITE_DOWN_MESSAGE);
                    } else {
                        await interaction.editReply(`❌ 查詢失敗或系統錯誤 (Code ${code})`);
                    }
                }
            } catch (e) { console.error("B50 回應失敗:", e.message); }
        });
    }

    // --- 指令 B: addfriend ---
    if (commandName === 'addfriend') {
        const FRIEND_CODE = interaction.options.getString('friendcode');

        const addProcess = spawn('python3', ['add_friend.py', FRIEND_CODE], {
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });

        let addResult = "";
        let addError = "";

        addProcess.stderr.on('data', (data) => {
            addError += data.toString();
        });

        addProcess.stdout.on('data', (data) => {
            const output = data.toString();
            addResult += output;
            const currentStatus = output.split('\n').filter(l => l.trim()).pop();
            if (currentStatus) {
                interaction.editReply(`🤖 **加好友進度**：${currentStatus}`).catch(() => {});
            }
        });

        addProcess.on('close', async (code) => {
            isProcessing = false; // 程序結束，解鎖
            if (!deferred) return;
            try {
                if (addResult.includes("SUCCESS_REQUEST_SENT")) {
                    await interaction.editReply(`✅ **申請成功**！機器人已向 \`${FRIEND_CODE}\` 送出好友邀請。`);
                } else if (addResult.includes("ERROR_WRONG_CODE")) {
                    await interaction.editReply(`❌ **申請失敗**：好友代碼錯誤。`);
                } else if (addResult.includes("ERROR_ALREADY_FRIEND_OR_FULL")) {
                    await interaction.editReply(`⚠️ **提示**：無法送出申請。可能已是好友或列表已滿。`);
                } else {
                    console.error(`add_friend.py 失敗 (Code ${code}):\n${tailLog(addError)}`);
                    if (SITE_DOWN_PATTERN.test(addError + addResult)) {
                        await interaction.editReply(SITE_DOWN_MESSAGE);
                    } else {
                        await interaction.editReply(`❌ **申請發生錯誤** (Code: ${code})。`);
                    }
                }
            } catch (e) { console.error("AddFriend 回應失敗:", e.message); }
        });
    }
});

client.on('error', console.error);
client.login(token);