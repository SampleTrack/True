class script(object):
    START_TXT = """𝙷𝙴𝙻𝙾 {},
𝙼𝚈 𝙽𝙰𝙼𝙴 𝙸𝚂 <a href=https://t.me/{}>{}</a>, 𝙸 𝙲𝙰𝙽 𝙿𝚁𝙾𝚅𝙸𝙳𝙴 𝙼𝙾𝚅𝙸𝙴𝚂, 𝙹𝚄𝚂𝚃 𝙰𝙳𝙳 𝙼𝙴 𝚃𝙾 𝚈𝙾𝚄𝚁 𝙶𝚁𝙾𝚄𝙿 𝙰𝙽𝙳 𝙴𝙽𝙹𝙾𝚈 😍"""
    HELP_TXT = """𝙷𝙴𝚈 {}
𝙷𝙴𝚁𝙴 𝙸𝚂 𝚃𝙷𝙴 𝙷𝙴𝙻𝙿 𝙵𝙾𝚁 𝙼𝚈 𝙲𝙾𝙼𝙼𝙰𝙽𝙳𝚂."""
    ABOUT_TXT = """✯ 𝙼𝚈 𝙽𝙰𝙼𝙴: {}
✯ 𝙲𝚁𝙴𝙰𝚃𝙾𝚁: 𝚄𝙽𝙺k𝙽𝙾𝚆𝙽
✯ 𝙻𝙸𝙱𝚁𝙰𝚁𝚈: 𝙿𝚈𝚁𝙾𝙶𝚁𝙰𝙼
✯ 𝙻𝙰𝙽𝙶𝚄𝙰𝙶𝙴: 𝙿𝚈𝚃𝙷𝙾𝙽 𝟹
✯ 𝙳𝙰𝚃𝙰 𝙱𝙰𝚂𝙴: 𝙼𝙾𝙽𝙶𝙾 𝙳𝙱
✯ 𝙱𝙾𝚃 𝚂𝙴𝚁𝚅𝙴𝚁: 𝙷𝙴𝚁𝙾𝙺𝚄
✯ 𝙱𝚄𝙸𝙻𝙳 𝚂𝚃𝙰𝚃𝚄𝚂: v1.0.1 [ 𝙱𝙴𝚃𝙰 ]"""
    SOURCE_TXT = """<b>NOTE:</b>
- Eva Maria not an open source project. 
- Source -   

<b>DEVS:</b>"""
    FORCE_SUB_TEXT = """**Please Join My Updates Channel to use this Bot!**","""
            
    MANUELFILTER_TXT = """Help: <b>Filters</b>

- Filter is the feature were users can set automated replies for a particular keyword and EvaMaria will respond whenever a keyword is found the message

<b>NOTE:</b>
1. eva maria should have admin privillage.
2. only admins can add filters in a chat.
3. alert buttons have a limit of 64 characters.

<b>Commands and Usage:</b>
• /filter - <code>add a filter in chat</code>
• /filters - <code>list all the filters of a chat</code>
• /del - <code>delete a specific filter in chat</code>
• /delall - <code>delete the whole filters in a chat (chat owner only)</code>"""
    BUTTON_TXT = """Help: <b>Buttons</b>

- Eva Maria Supports both url and alert inline buttons.

<b>NOTE:</b>
1. Telegram will not allows you to send buttons without any content, so content is mandatory.
2. Eva Maria supports buttons with any telegram media type.
3. Buttons should be properly parsed as markdown format

<b>URL buttons:</b>
<code>[Button Text](buttonurl:https://t.me/XYZ)</code>

<b>Alert buttons:</b>
<code>[Button Text](buttonalert:This is an alert message)</code>"""
    AUTOFILTER_TXT = """Help: <b>Auto Filter</b>

<b>NOTE:</b>
1. Make me the admin of your channel if it's private.
2. make sure that your channel does not contains camrips, porn and fake files.
3. Forward the last message to me with quotes.
 I'll add all the files in that channel to my db."""
    CONNECTION_TXT = """Help: <b>Connections</b>

- Used to connect bot to PM for managing filters 
- it helps to avoid spamming in groups.

<b>NOTE:</b>
1. Only admins can add a connection.
2. Send <code>/connect</code> for connecting me to ur PM

<b>Commands and Usage:</b>
• /connect  - <code>connect a particular chat to your PM</code>
• /disconnect  - <code>disconnect from a chat</code>
• /connections - <code>list all your connections</code>"""
    EXTRAMOD_TXT = """Help: <b>Extra Modules</b>

<b>NOTE:</b>
these are the extra features of Eva Maria

<b>Commands and Usage:</b>
• /id - <code>get id of a specified user.</code>
• /info  - <code>get information about a user.</code>
• /imdb  - <code>get the film information from IMDb source.</code>
• /search  - <code>get the film information from various sources.</code>"""
    ADMIN_TXT = """Help: <b>Admin mods</b>

<b>NOTE:</b>
This module only works for my admins

<b>Commands and Usage:</b>
• /logs - <code>to get the rescent errors</code>
• /stats - <code>to get status of files in db.</code>
• /delete - <code>to delete a specific file from db.</code>
• /users - <code>to get list of my users and ids.</code>
• /chats - <code>to get list of the my chats and ids </code>
• /leave  - <code>to leave from a chat.</code>
• /disable  -  <code>do disable a chat.</code>
• /ban  - <code>to ban a user.</code>
• /unban  - <code>to unban a user.</code>
• /channel - <code>to get list of total connected channels</code>
• /broadcast - <code>to broadcast a message to all users</code>"""
    STATUS_TXT = """★ 𝚃𝙾𝚃𝙰𝙻 𝙵𝙸𝙻𝙴𝚂: <code>{}</code>
★ 𝚃𝙾𝚃𝙰𝙻 𝚄𝚂𝙴𝚁𝚂: <code>{}</code>
★ 𝚃𝙾𝚃𝙰𝙻 𝙲𝙷𝙰𝚃𝚂: <code>{}</code>
★ 𝚄𝚂𝙴𝙳 𝚂𝚃𝙾𝚁𝙰𝙶𝙴: <code>{}</code> 𝙼𝚒𝙱
★ 𝙵𝚁𝙴𝙴 𝚂𝚃𝙾𝚁𝙰𝙶𝙴: <code>{}</code> 𝙼𝚒𝙱"""
    VERIFY_MSG = """
Hey {a}💕 

Temporary Token has been expired, Kindly generate Temp Token to start using bots Again. And Get access of unlimited Movies For Next 12 Hours.

Validity :- 12 hours"""
    VERIFY_SUC = """
Congratulations {a}! Ads Token Refreshed Successfully! Now Enjoy Bot Without any Ads and Access Unlimited Movies For Next 12 Hours.

It Will Expire After 12 hours."""
    FILE_MSG = """
<b>Hai 👋 {} </b>😍

<b>📫 Your File is Ready</b>

<b>📂 Fɪʟᴇ Nᴀᴍᴇ</b> : <code>{}</code>

<b>⚙️ Fɪʟᴇ Sɪᴢᴇ</b> : <b>{}</b>"""
    CHANNEL_CAP = """
<b>Hai 👋 {}</b> 😍

<code>{}</code>

<b>Dᴜᴇ ᴛᴏ ᴄᴏᴘʏʀɪɢʜᴛ ᴛʜᴇ ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ʜᴇʀᴇ ɪɴ 10 ᴍɪɴᴜᴛᴇs sᴏ ᴅᴏᴡɴʟᴏᴀᴅ ᴀғᴛᴇʀ ᴍᴏᴠɪɴɢ ғʀᴏᴍ ʜᴇʀᴇ ᴛᴏ sᴏᴍᴇᴡʜᴇʀᴇ ᴇʟsᴇ!</b>

<b>© Powered by {}</b>"""
    LOG_TEXT_G = """#NewGroup 😎

Group: {a}
Group ID: <code>{b}</code>
Group UN: @{c}

Total Members: <code>{d}</code>
Total Groups: <code>{e}</code>
Today Groups: <code>{f}</code>

Date: <code>{g}</code>
Time: <code>{h}</code>

Added By: {i}
By @{j}

#{j}"""
    LOG_TEXT_P = """#NewUsers 😀
    
ID: <code>{a}</code>
Name: {b}
Username: @{c}

Total Users: {d}
Today Users: {e}

Date: <code>{f}</code>
Time: <code>{g}</code>

By @{h}"""
    NEW_MEMBER = """#NewMember 😀

Group = {a}
Group ID = <code>{b}</code>
Group UN = @{c}
Total Member = <code>{d}</code>
Invite = {e}
           
Member = {f}
Member ID = <code>{g}</code>
Member UN = @{h}

Date = <code>{i}</code>
Time = <code>{j}</code>

#{k}"""
    LEFT_MEMBER = """#LeftMember 😔

Group = {a}
Group ID = <code>{b}</code>
Group UN = @{c}
Total Member = <code>{d}</code>
Invite = {e}
           
Member = {f}
Member ID = <code>{g}</code>
Member UN = @{h}

Date = <code>{i}</code>
Time = <code>{j}</code>

#{k}"""
    REPORT_TXT = """#Daily_Report

Date = {a}
Time = {c}

Total
Total Users = <code>{d}</code>
Total Chats = <code>{e}</code>

Yesterday
{b} Users = <code>{f}</code>
{b} Chats = <code>{g}</code>

Yesterday
{b} Active Users = <code>{h}</code>
{b} Active users Percentage = <code>{i}</code>

#{j}"""
    RESTART_TXT = """#Restarted

🔄 Bot Restarted!
📅 Date: <code>{a}</code>
⏰ Time: <code>{b}</code>
🌐 Timezone: <code>Asia/Kolkata</code>

#{c}"""
