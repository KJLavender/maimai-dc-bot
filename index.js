const fs = require('fs');
const { Client, Events, GatewayIntentBits, REST, Routes, SlashCommandBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
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
        .setDescription('查看你目前綁定的 maimai 好友ID')
].map(command => command.toJSON());

const rest = new REST({ version: '10' }).setToken(token);

client.once(Events.ClientReady, async (readyClient) => {
    console.log(`✅ Ready! Logged in as ${readyClient.user.tag}`);
    try {
        await rest.put(Routes.applicationGuildCommands(clientId, guildId), { body: commands });
        console.log('成功註冊指令：/b50, /addfriend, /m, /bind, /unbind, /myid');
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
                    await interaction.editReply(`❌ 查詢失敗或系統錯誤 (Code ${code})`);
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
                    await interaction.editReply(`❌ **申請發生錯誤** (Code: ${code})。`);
                }
            } catch (e) { console.error("AddFriend 回應失敗:", e.message); }
        });
    }

    // --- 指令 C: m (歌曲定數查詢，含按鈕選歌) ---
    if (commandName === 'm') {
        const query = interaction.options.getString('query');

        const searchProcess = spawn('python3', ['search_song.py', query], {
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });

        let searchResult = "";

        searchProcess.stdout.on('data', (data) => {
            searchResult += data.toString();
        });

        searchProcess.stderr.on('data', (data) => {
            console.error("search_song.py stderr:", data.toString());
        });

        searchProcess.on('close', async (code) => {
            isProcessing = false;
            if (!deferred) return;
            try {
                if (code !== 0 || !searchResult.trim()) {
                    return interaction.editReply(`❌ 找不到與「${query}」相關的歌曲。`);
                }

                const data = JSON.parse(searchResult.trim());
                if (data.error) {
                    return interaction.editReply(`❌ 找不到與「${query}」相關的歌曲。`);
                }

                const results = data.results;

                // 只有一首 → 直接顯示
                if (results.length === 1) {
                    const song = results[0];
                    const embed = new EmbedBuilder()
                        .setTitle(`🎵 ${song.title}`)
                        .setColor(0xFFD700)
                        .addFields(
                            { name: '藝術家', value: song.artist, inline: true },
                            { name: '📊 譜面定數', value: song.levels.join('\n') || '無資料', inline: false }
                        );
                    return interaction.editReply({ embeds: [embed] });
                }

                // 多首 → 顯示按鈕讓使用者選擇
                const descLines = results.map((s, i) => `**${i + 1}.** ${s.title} — ${s.artist}`);
                const embed = new EmbedBuilder()
                    .setTitle(`🔍 搜尋「${query}」的結果`)
                    .setDescription(descLines.join('\n'))
                    .setColor(0x3498DB)
                    .setFooter({ text: '請點擊下方按鈕選擇歌曲' });

                const row = new ActionRowBuilder();
                results.forEach((song, i) => {
                    row.addComponents(
                        new ButtonBuilder()
                            .setCustomId(`song_${i}`)
                            .setLabel(`${i + 1}. ${song.title}`.substring(0, 80))
                            .setStyle(ButtonStyle.Primary)
                    );
                });

                const response = await interaction.editReply({ embeds: [embed], components: [row] });

                // 等待按鈕點擊 (60秒)
                const collector = response.createMessageComponentCollector({ time: 60000 });

                collector.on('collect', async (btnInteraction) => {
                    const idx = parseInt(btnInteraction.customId.split('_')[1]);
                    const song = results[idx];
                    if (!song) return;

                    const songEmbed = new EmbedBuilder()
                        .setTitle(`🎵 ${song.title}`)
                        .setColor(0xFFD700)
                        .addFields(
                            { name: '藝術家', value: song.artist, inline: true },
                            { name: '📊 譜面定數', value: song.levels.join('\n') || '無資料', inline: false }
                        );
                    await btnInteraction.reply({ embeds: [songEmbed] });
                });

                collector.on('end', () => {
                    interaction.editReply({ components: [] }).catch(() => {});
                });

            } catch (e) { console.error("M 搜尋回應失敗:", e.message); }
        });
    }
});

client.on('error', console.error);
client.login(token);