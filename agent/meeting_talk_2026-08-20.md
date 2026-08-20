# Meeting script — 2026-08-20 ｜ 会议讲稿

**约 10 分钟。** 跟着 `agent/gps_fleet_agent.ipynb` 讲，重启 kernel 从头跑一遍再开始。
**中文是对照**，用来确认自己讲到哪。

范围：**只讲 BN**。Middling 和 Reject 的情况留到问答，讲法见最后一节。

---

## 1 ｜ 这个 agent 拿什么、给什么、干什么用

**EN.**
Last week I showed the method. This week it is wired into the notebook, so let me start with
what goes in and what comes out.

What goes in is one question in plain English, and optionally a period — a month, or a whole
year. Nothing else. No dashboard, no parameters to set.

What comes out is a short answer to one question: what should we fix first. It names the one
or two things worth the most, says how many extra loads per day each is worth, and says
plainly that those numbers are upper bounds, not forecasts.

The purpose is the part I want to be clear about. The four specialists we already had answer
what the fleet did — how long a cycle takes, how much idle there is, which routes are used.
None of them answers what to do about it. That is the gap this fills. It is the difference
between a report and a recommendation.

**中.** 上周讲的是方法，这周它接进 notebook 了，所以先说**输入和输出**。

**输入**：一句英文问题，外加一个可选的时间范围——某个月，或者整年。就这些。没有仪表盘，没有要调的参数。

**输出**：对一个问题的简短回答——**该先修什么**。它点出最值钱的一两项，说每项每天能多拉几车，并且明说**那些数是上界，不是预测**。

**目的**是我想讲清楚的地方。原来那四个专家回答的是**车队做了什么**——一圈多久、空转多少、走哪条路。**没有一个回答"那该怎么办"。** 这就是它补的位置。这是报告和建议的区别。

---

## 2 ｜ 它接在图上的哪个位置

**EN.**
Show the graph. There are six boxes. The router reads the question and picks one.

We added one box — diagnosis — and one line to the router that tells it when to pick that box.
The rule is: how much idle is there goes to the idle specialist; why, and what to do, comes
here.

The important part is what is not in this picture. None of the six boxes computes anything.
They all read files. The work happens offline, in two scripts that run beforehand.
Building the trip table from raw GPS and spreading every ping across the stations takes about
half a minute for one month — that cannot happen inside a chat turn. So it is precomputed into
a small file, and the box in the diagram only reads it.

That is the same contract the other four boxes already had. We did not change how the notebook
works; we added a fifth thing for it to read.

**中.** 放那张图。六个盒子，router 读问题选一个。

**我们加了一个盒子（diagnosis），和 router 里的一行规则**告诉它什么时候选这个盒子。规则是：**"空转有多少"去空转专家，"为什么、该怎么办"来这里。**

重要的是**图上没画出来的东西**。这六个盒子**没有一个在算东西，它们全是读文件**。真正的计算在提前跑的两个离线脚本里。从原始 GPS 建趟次表、再把每个 ping 摊到各个站点上，**单月大约半分钟**——这在一轮对话里跑不完。所以先算好写成一个小文件，图上那个盒子只负责读。

**这跟原来四个盒子是同一套约定。** 我们没有改 notebook 的工作方式，只是多给它一样东西读。

---

## 3 ｜ 结果长什么样

**EN.**
Run it two ways. First one month.

    ask("What should we fix first?", month="2025-08")

August has a clear single answer: the queue at the weighbridge and tarping point, worth about
plus twelve point seven loads a day, ahead of the next thing by seven point three.

Now the whole year.

    ask("What can be done to improve efficiency?", year="2025")

Five months pooled — a hundred and fifty-three days, twelve thousand five hundred loads. Here
the answer is different in a way that matters. Two things are tied for first: the same queue at
plus seven point six, and trucks stopping at places the mine has drawn no zone for, at plus
four point nine. The gap between them is two point seven loads a day, and the ranking cannot
resolve anything under five, so we report them together and refuse to pick one.

The year view carries one column a single month cannot: where each item ranked in each of the
five months. The leading item was first in four months out of five. In October it was second.
We report that rather than smoothing it away — if we had only looked at October we would have
named a different winner.

One more result, and it is the sturdiest one here. Shovel utilisation ran between zero point
four two and zero point six three across the five months. Not one month came close to
saturation. So the queueing is a question of when trucks arrive, not of the shovel being too
small. This is the only conclusion that has survived every correction we have made to the
method, and it is the one I would defend hardest. It also means: do not buy equipment on the
strength of this.

**中.** 跑两遍。**先跑一个月。**

八月有一个**明确的单一答案**：过磅点和苫盖点那里的排队，约 **+12.7 车/天**，领先第二名 **7.3**。

**再跑整年。** 五个月合并——**153 天、12,593 车次**。这里的答案不一样，而且这个不一样很重要：**两项并列第一**——同一个排队 **+7.6**，和卡车停在矿方没画区域的地方 **+4.9**。两者差 **2.7 车/天**，而这个排序**分辨不了 5 以下的差距**，所以我们把它们并列报出来，**拒绝挑一个**。

年视图多一列是单月给不了的：**每一项在五个月里各自排第几**。第一名的那项**五个月里有四个月排第一，十月排第二**。我们**把这个报出来，而不是抹平**——如果只看十月，我们会说出另一个第一名。

**还有一个结果，是这里面最硬的。** 铲车利用率五个月在 **0.42 到 0.63** 之间，**没有任何一个月接近饱和**。所以排队是**卡车什么时候到**的问题，不是铲车太小。**这是我们对方法做的每一次修正之后都没变的唯一结论**，也是我最有把握的一条。它同时意味着：**不要凭这个去买设备。**

---

## 4 ｜ 用了 Uka 的 DBSCAN

**EN.**
The second of those two tied items came out of Uranbileg's code, not ours.

We could measure that trucks were standing still somewhere for three thousand seven hundred
truck-hours across the year, but we had no name for the place — the mine has drawn no polygon
there, so our zone lookup returns nothing. Uranbileg's clustering function groups stop points
into clusters and gives back a centre. We call it directly from the shared library.

That turns an unusable finding into a usable one. The largest cluster is nine hundred and ten
truck-hours at forty-three point six five four two five, one hundred and five point five zero
six three four. It shows up in four of the five months, with up to twenty-five different
trucks. It is two hundred and ninety-three metres from the weighbridge.

We deliberately do not say what it is. We tested three explanations and none of them held, so
we hand over the coordinate as a question for the site. That is the honest form of it, and it
is a question somebody at the mine can answer in one sentence.

Two other things of Uranbileg's are in here as well: the trip-building code is now one shared
function that both pipelines call, and the daily and monthly tables the other four specialists
read are hers.

**中.** 并列的**第二项是从 Uranbileg 的代码里出来的**，不是我们的。

我们能测出卡车全年有 **3,722 车小时**停在某个地方不动，但**说不出那是哪儿**——矿方没在那画多边形，我们查区域什么都查不到。**Uranbileg 的聚类函数**把停车点聚成团、给出中心点。我们**直接从共享库里调用它**。

**这把一个没法用的发现变成了能用的。** 最大的一团是 **910 车小时**，在 **43.65425, 105.50634**，**五个月里出现四个月，最多 25 台不同的车**，离过磅点 **293 米**。

**我们故意不说那是什么。** 我们试了三种解释，**没有一个站得住**，所以我们把坐标当成一个问题交给现场。**这是诚实的讲法**，而且这个问题矿上的人一句话就能回答。

Uranbileg 的东西还有两处在里面：**建趟次的代码现在是一个共享函数**，两条流水线都调它；**另外四个专家读的日表和月表是她做的。**

---

## 5 ｜ 写作：建议用 LaTeX，共用一个 Overleaf

**EN.**
Last thing, and it is about writing rather than code. I talked with Uranbileg and we would both
prefer to write in LaTeX and share one Overleaf project.

The reason is simply that we are two people editing one document with a lot of tables and
numbers in it. Right now the numbers live in our code and get copied into the text by hand,
which is how the version in the draft got out of step. With a shared project we both edit the
same source, and the tables can be regenerated rather than retyped.

If that is fine with you, I will set up the project and send the invitation.

**中.** 最后一件，是**写作不是代码**。我跟 Uranbileg 聊过，**我们俩都倾向用 LaTeX，共用一个 Overleaf 项目**。

理由很简单：**两个人在改同一份带大量表格和数字的文档**。现在数字在代码里，靠手工抄进正文——**草稿里那份就是这么脱节的**。共享项目的话，两个人改同一份源文件，**表格可以重新生成而不是重打**。

**如果您觉得可以，我来建项目发邀请。**

---

## 备用 ｜ 被问到再讲

**Middling / Reject 为什么不讲。** 它们不是 BN 的缩小版，是不同性质的作业：BN 运距 34 公里，
Middling 是 0.4 公里。0.4 公里的循环上，路段分解和站点发现这两层没有东西可测。而且这两条流
三分之一的时间 GPS 没记录。**这是方法的边界，能讲清楚，不用遮。**
唯一值得查的：Reject 卸车中位 11.2 分钟，BN 是 1.6——七倍，还没查过。

**为什么并列而不排第一。** 参数扫描里名次翻转**只发生在 5 车/天以内**，超过 5 的领先没被翻过。
所以 5 以下的领先不是信息，是参数抖动。八月领先 7.3，我们就报了单独第一名。

**天花板是多少。** 不报。它在**参数合理范围内从 125 变到 273 车/天**，只有"没饱和"这一条站得住。

---

## 加的一节 ｜ 共享代码改了，Uka 的数字会变

*这一节不在原定提纲里。加它是因为如果 Uranbileg 在场而这件事没说，她之后会自己撞上。
她不在场就删掉，改成会后单独发消息。*

**EN.**
One thing I owe Uranbileg. The trip-building code is shared, and we found three defects in it
and fixed them. Her pipeline calls the same function, so her numbers move.

The largest one: trips longer than six hours were being discarded as a tracker being switched
off. On BN in November that threw away two hundred and eighty-six trips out of two thousand
six hundred and ninety-eight, and their time was handed to the next trip's dwell. It is not a
safe test, because more than half of the discarded trips had continuous GPS the whole way. We
now keep every trip and record whether there was a gap in the signal, which is the thing that
actually distinguishes the two.

The effect on the daily tables: mean dump time goes from eighteen point nine minutes to four
point seven. The old figure was mostly a truck sitting somewhere else.

I have not asked her to change anything yet — I wanted to raise it here first, and I will send
her the detail.

**中.** 有件事我欠 Uranbileg 一个交代。**建趟次的代码是共享的**，我们在里面发现三个缺陷并修好了。**她的流水线调的是同一个函数，所以她的数字会变。**

**最大的一个**：超过六小时的趟被当成"记录仪关机"扔掉。BN 十一月**2698 趟里扔掉了 286 趟**，它们的时间被并进了下一趟的停留。**这个判据不安全，因为被扔掉的趟里一半以上全程 GPS 是连续的。** 现在**全部保留**，改成记录"信号有没有断口"——那才是真正能区分两者的东西。

**对日表的影响：卸车均值从 18.9 分钟变成 4.7 分钟。** 原来那个数大部分是卡车停在别的地方。

**我还没要求她改任何东西**——想先在这里提出来，细节我发给她。
