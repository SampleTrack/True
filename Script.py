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
    
    FORCE_SUB_TEXT = """
        🚀 **Limited Time Offer!**
        Join our updates channel now to unlock **1 Month of Premium Access** for free. This offer is valid only for new members today!
        ⚠️ **Membership is required** to verify your account and prevent bot abuse."""
    
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
    MELCOW_ENG = """𝙷𝙴𝙻𝙻𝙾 {a}, 𝚆𝙴𝙻𝙲𝙾𝙼𝙴 𝚃𝙾 {b}!""" 
    
