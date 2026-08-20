# Talking script ｜ 讲稿

**配合 `agent_method_EN.md` 使用。** 文档里的细节比这份多——**讲的时候只讲这 13 节，剩下的留给对方自己看或者提问时再展开。**

**中文是对照**，用来确认自己讲到哪。约 **15 分钟**。

**砍掉不讲的**（文档里有，讲的时候跳过）：卡车和区域怎么识别、四个相位的定义细节、作业小时的 0.4、站点速率的算法、站点时间三分、报告前的第 3 和第 4 条规则。这些被问到再说。

---

## 1 ｜ 这是什么 What this is

**EN.**
We have GPS from the haul trucks. That is all we have.
No payload data, no fuel data, no dispatch records.
From that, we want to answer one question: where does this fleet lose time?
And not just where. We also want to rank it — what is worth the most to fix.
The output is a list. Each item says how many extra loads per day you would get.
One thing about scope before I start. Everything I show is one load zone — BN — in November. That is the example. The same code ran on all five months we hold, with nothing adjusted between them, and I will come back to what that showed at the end.
I will go through how we get from raw GPS to that list.

**中.** 我们有卡车的 GPS，就只有这个。没有载重、没有油耗、没有调度记录。我们想回答一个问题：**这支车队的时间损失在哪。** 不只是"在哪"，还要排序——哪一项最值得改。**输出是一张表，每一项写着修好它每天能多拉几车。**

**开始之前先说清楚范围**：我展示的全部是**一个装车区（BN）、十一月**，那是**举例**。**同一套代码跑了我们手上全部五个月，中间什么都没调**，最后我会回来说那个结果。

我讲一下从原始 GPS 怎么走到这张表。

---

## 2 ｜ 从点位到一趟车 From pings to trips

**EN.**
The GPS gives a position every twelve seconds. The mine has drawn zones on the map, so we check every point — inside a zone or not — and read the sequence: sits in the load zone, moves, sits in the dump zone, comes back.
That is one trip, and it splits into four parts we have exact boundaries for: the stay at the load zone, the loaded haul, the dump, and the empty return. Medians here are 21 minutes, 72, 2 and 94.
For this load zone in November that gives 2 657 trips, from 22 trucks, over 30 days.

**中.** GPS 每 12 秒给一个位置。矿方在地图上画了区域，所以我们对每个点问"在不在区域里"，然后读顺序——待在装车区、移动、待在卸点、回来。

**这就是一趟。** 它分成四段，每个边界的时刻我们都有：**装车停留、重载去程、卸车、空车回程**，中位分别是 **21、72、2、94 分钟**。

这个装车区，十一月：**2657 趟，22 台车，30 天**。

---

## 3 ｜ ⭐ 但"用了多久"不等于"开了多久" The problem with those durations

**EN.**
Now here is the thing that took us a while to notice.
Look at that return phase: 94 minutes. It is tempting to say the road is slow.
But that 94 minutes is just two timestamps subtracted. When the truck left the dump, and when it got back.
It tells you nothing about what happened in between.
Let me show you one real trip. Truck 51036, on the sixth of November.
It left the dump at 04:05 and got back at 08:44. So 279 minutes.
But when we look at the GPS second by second: it sat on the stockpile for 11 minutes.
Then it drove for 12.
Then it sat at a car park for 164 minutes.
Then it drove for 34.
Then it sat at the gate into the pit for 24, and at a tarping point for 8.
So: 46 minutes of driving. 233 minutes of standing still.
Across the whole month, only 43 percent of that so-called road time is a truck actually driving.
So before we can say anything about delay, we have to find out where the rest goes.

**中.** 有一件事我们花了一阵才注意到。看那个回程：94 分钟，很容易就说"路慢"。**但这 94 分钟只是两个时间戳相减**——车什么时候离开卸点、什么时候回来。**它完全不告诉你中间发生了什么。**

举一趟真的。51036 号车，11 月 6 日。04:05 离开卸点，08:44 回来，279 分钟。但把 GPS 一秒一秒看下去：**在料堆上停了 11 分钟**，开 12 分钟，**在停车场坐了 164 分钟**，又开 34 分钟，**在采场门口停 24 分钟**，**在盖篷布点停 8 分钟**。

**开车 46 分钟，停着 233 分钟。**

整月看，所谓"路上时间"里只有 **43%** 是卡车真在开车。**所以在谈延误之前，得先搞清楚剩下的去了哪。**

---

## 4 ｜ 那条路上到底有什么 What is actually on that road

**EN.**
The mine has drawn 104 zones on the map, not just the load and dump zones.
Weighbridges, car parks, junctions, and so on.
But we do not know what any of them are used for. We cannot ask the site, and the names are in Mongolian.
So instead of guessing, we ask the GPS two questions about each of those 104 places.
First: does every trip pass through here?
We count how many times trucks visit it, and divide by the number of trips.
If a place is on the route, and trucks pass it on the way out and on the way back, it scores about 200 percent.
Second: do the trucks actually stop there, or just drive through?
We check whether the speed drops to almost zero.
Those two questions sort the 104 places into three groups.
Some are passed every trip, and trucks stop — five of them. Two weighbridges, two tarping points, and the gate into the pit.
Some are passed every trip, but nobody stops — junctions and turns. Those are just points on the road.
And some are not on every trip at all. The car park is visited on 40 percent of trips, for about 11 minutes. The repair yard on 11 percent — but for a median of 100 minutes when it happens.
That last group has to be taken out of the loop entirely, and I will explain why on the next point.

**中.** 矿方在地图上画了 **104 个区域**，不只是装车区和卸点——还有过磅站、停车场、路口等等。**但我们不知道它们是干什么用的**：问不到现场，名字又是蒙文。

所以我们不猜，而是**对这 104 个地方，向 GPS 问两个问题**。

**第一：是不是每趟都经过？** 数一下卡车访问了多少次，除以总趟数。如果一个地方在路线上，去程回程各过一次，就是约 200%。

**第二：车是真停下来了，还是只是开过去？** 看速度有没有降到接近零。

这两个问题把 104 个地方分成三组：**每趟都过、而且车会停**——五个：两个过磅站、两个盖篷布点、进采场的门口。**每趟都过、但没人停**——路口、转弯，那就是路上的点而已。**还有一些根本不是每趟都去**——停车场 40% 的趟会去、每次约 11 分钟；维修厂只有 11% 的趟会去，**但一去中位就是 100 分钟**。**最后这一组必须整个移出循环**，下一节说为什么。

---

## 5 ｜ ⭐ 延误是跟什么比出来的 What "delay" is measured against

**EN.**
Now, how do we decide that some time was wasted?
We never compare against a manufacturer's number, or a target somebody set.
We compare each truck against what this same fleet does when nothing is in the way.
For driving on the road: we take the fastest 15 percent of trips, and use that as the free-flow time.
But — and this is the point of the last section — we only count time when the truck was actually moving. Not the parked time.
For loading, and for a weighbridge or a tarping point, we do something better than a percentile.
We look at all the visits where no other truck was there, and take the median. That is the service time — measured directly, not chosen. At the load zone it is 13 minutes.
Now back to the car park.
The reference for the road comes from the fastest trips. And the fastest trips do not stop at the car park.
So if we leave them inside the road, a 100-minute stop at the repair yard gets counted as road delay.
And the recommendation would come out as "fix the road" — when what actually happened is a shift change.
That is why anything that is not on every trip has to come out.

**中.** 那我们怎么判断某段时间是浪费的？**我们从不跟厂家参数比，也不跟谁定的目标比。我们拿每台车跟"这支车队自己在没有阻碍时的表现"比。**

**路上行驶**：取最快的 15% 的趟数，当作自由流时间。**但是**——这就是上一节的意义——**我们只算车真的在动的那部分时间，不算停着的**。

**装车、过磅站、盖篷布点**：这里我们用了比分位数更好的办法。**看所有"没有别的车在场"的访问，取中位时长，那就是服务时间。** 这是直接量出来的，不是挑的。装车区是 **13 分钟**。

再回到停车场。**路的参照来自最快的那批趟，而最快的那批趟不会去停车场。** 所以如果把它们留在"路"里面，**在维修厂停的那 100 分钟会被算成路上延误**，建议就会变成"去修路"——而实际是车在等修。**这就是为什么不是每趟都有的东西必须拿出去。**

---

## 6 ｜ 排队，还是装车本来就慢 Queue, or just slow loading

**EN.**
At the load zone the stay mixes loading with waiting, and duration alone cannot separate them — a 13-minute stay and a 32-minute stay look like the same kind of event.
So the test is not how long the truck waited. It is how many trucks were already there when it arrived. Nobody there, that is service. Someone ahead, the excess is a queue. Same rule at the weighbridges and tarping points.
And it checks out cleanly: with nobody ahead the median stay is 13 minutes, one truck 16, two 20, three 26, four 32, five or more 40. That is about as clean a dose-response as observational data gives, and it is the strongest single piece of evidence in the analysis.

**中.** 装车区的停留把"装车"和"等待"混在一起，**光看时长分不开**——13 分钟和 32 分钟看上去是同一类事件。

**所以判据不是等了多久，是到达那一刻前面有几台车。** 没车就是服务时间，有车挡着，多出来的就是排队。过磅站和盖篷布点同理。

**而且验得很干净**：前面没车 13 分钟，一台 16，两台 20，三台 26，四台 32，五台以上 40。**这是观测数据能给出的最干净的剂量-反应关系，也是整个分析里最强的一条证据。**

---

## 7 ｜ 铲车是不是瓶颈 Is the shovel the limit?

**EN.**
There is an obvious question here. Maybe there is a queue because the shovel simply cannot load fast enough.
So we measured that. We looked at how quickly trucks leave the load zone when the shovel is busy.
The answer is one truck every 7.9 minutes. So 7.58 an hour.
And how many is it actually doing? 4.22 an hour.
So the shovel is working a bit over half the time. It is idle for the rest.
That is the interesting part. There is a queue in front of it, and it is idle half the time.
Those two things together mean one thing: the trucks are not arriving evenly.
They come in bunches. The shovel is swamped, then it waits, then it is swamped again.
So a bigger shovel would not help. The problem is the timing of arrivals.

**中.** 这里有个明显的问题：**会不会就是因为铲车装不过来，所以才排队？**

所以我们量了一下：铲车忙的时候，卡车多久离开一次装车区。答案是**每 7.9 分钟一台，也就是每小时 7.58 台**。那它实际在做多少？**每小时 4.22 台**。

**所以铲车有一半多一点的时间在干活，其余闲着。**

**这才是有意思的地方：它前面排着队，而它有一半时间是闲的。** 这两件事放一起只说明一件事——**卡车到得不均匀**。它们成堆地来，铲车被淹一阵，然后等一阵，然后又被淹。

**所以换个更大的铲车没有用，问题在到达的时间分布。**

---

## 8 ｜ 把小时换成"每天几车" Turning hours into loads per day

**EN.**
Now we have delays, but they are in truck-hours. That is hard to compare across different causes.
So we convert everything into the same unit: extra loads per day.
The logic is simple. This fleet puts 417 truck-hours into the loop every day.
One full loop currently takes 282 minutes. That works out to 88.6 loads a day.
Now suppose we remove the queue at the load zone. The loop drops to 271 minutes.
Same 417 hours, shorter loop — so 92.2 loads a day.
That is 3.6 more loads, from that one fix.
We do this for every cause, and then we rank them.
One warning about the ranking. You cannot add these numbers up.
Each one assumes the others stay as they are. If you fixed everything at once you would get more than the sum, not less.
So we use the list to decide what to do first. Not to promise a total.

**中.** 现在我们有了延误，但单位是卡车小时，不同原因之间没法比。**所以全部换成同一个单位：每天多几车。**

逻辑很简单。这支车队每天往循环里投 **417 卡车小时**。现在跑一圈要 282 分钟，算下来是 **88.6 车/天**。

假设我们去掉装车区的排队，一圈变成 271 分钟。**同样的 417 小时，圈短了，就是 92.2 车/天。** 也就是**这一项值 3.6 车/天**。

每个原因都这么算一遍，然后排序。

**关于排序有一个提醒：这些数字不能相加。** 每一项都假设别的不变。如果全部一起修，得到的会**比相加还多**，不是更少。**所以这张表是用来决定先做什么的，不是用来承诺一个总数的。**

---

## 9 ｜ 结果 The result

**EN.**
For November, at this load zone, here is what comes out — and the honest headline is that nothing wins.
Two items are level at the top, both worth about 5.8 loads a day. One is the queue at the weighbridge and tarping point on the dump side. The other is trucks standing still in places the mine has never drawn a zone around.
Then the queue at the shovel at 3.6, and the queue at the pit-side stations at 3.5.
The two road items — the actual driving — are fifth and sixth, worth 2.5 and 2.
So the road is not the problem here. Once you take the parked time out of it, the driving is efficient. Empty trucks drive faster than loaded ones — 58 minutes against 60 — which is what you would expect physically.
So four items are worth roughly the same, and our own rule says we do not name a winner unless it leads by five loads a day. It does not. So we report a group, not a ranking.
The second of those two leading items deserves a comment. It is not a finding about the operation — it is a gap in the data. Only 11 of the 104 zones have a real outline drawn. Getting the rest would resolve the largest single item on our list.
One more thing. There are two items we deliberately keep out of the ranking: time trucks spend stopped off the loop, and phase time the GPS never recorded at all. Both are larger than any lever. Neither is something a dispatcher can act on.

**中.** 十一月，这个装车区，结果是这样——**而诚实的说法是：没有第一名。**

**并列第一的有两项，各约 5.8 车/天。** 一个是卸点侧过磅站和盖篷布点的排队，另一个是**卡车停在矿方从来没画过区域的地方**。然后是装车区排队 3.6、采场侧站点排队 3.5。**两条路——真正的行驶——排第五第六，值 2.5 和 2。**

**所以路在这里不是问题。** 把停着的时间拿掉之后，行驶是高效的。**空车比重载开得快**——58 分钟对 60 分钟——这才符合物理常识。

**四项差不多大。而我们自己的规矩是：领先不到 5 车/天就不点名。它没领先到。所以我们报一组，不报排名。**

**并列第一里的第二项值得单独说一句：它不是关于作业的发现，是数据的缺口。** 104 个区域里只有 11 个画了真实轮廓。**把其余的拿到，就能解掉我们表上最大的一项。**

还有一点。**有两项我们刻意不放进排序**：卡车停在循环外的时间，以及 **GPS 根本没记录到的那部分时间**。**两项都比任何一个杠杆大，但都不是调度员能动的。**

---

## 10 ｜ 能提升多少 How much is recoverable

**EN.**
Naturally the next question is: how much is all this worth in total?
We give two numbers, not one, because we cannot honestly give a single one.
The lower one is plus 21 percent. Here is what that means.
We took the 26 normal working days in November and found the best one: 120 loads, against an average of 98.8.
If every normal day matched that best day, output would be 21 percent higher.
That number has something behind it — that day actually happened. So we know it is achievable.
About 6 points of it come from having more trucks out on the day, which is a maintenance question.
The other 13 points come from each truck doing more trips. That is the part that depends on how they are dispatched.
The higher number is plus 38 percent. That is if every delay we identified disappeared at once.
That has never happened, and it never will. We report it as an upper limit, not as a target.
Separately from all this: four days in November were near-shutdowns. Those four days cost 12 percent of the month's output.
That is bigger than any of our items. But it is a maintenance or weather problem, not a dispatch one.

**中.** 接下来自然的问题是：**这些加起来值多少？** 我们给**两个数，不是一个**，因为诚实地说给不出一个。

**低的那个是 +21%。** 意思是：我们把十一月 **26 个正常工作日**拿出来，找出最好的那一天——**120 车，而平均是 98.8**。**如果每个正常日都做到那一天，产量就高 21%。** 这个数是有依据的——**那一天真的发生过，所以我们知道它能做到。**

其中约 **6 个百分点**来自那天出勤的车更多，**那是维修的问题**。另 **13 个百分点**来自每台车多跑了几趟，**那部分才取决于怎么调度**。

**高的那个是 +38%**，意思是我们找出的所有延误一次全部消失。**那从没发生过，也不会发生。我们把它当上限报，不是当目标。**

另外单独说一件事：**十一月有四天几乎停产，那四天占掉了全月产量的 12%。** 比我们任何一项都大，**但那是维修或天气的问题，不是调度的**。

---

## 11 ｜ 这些结论稳不稳 How much of this holds up

**EN.**
Two things we did to check ourselves.
First, the same code on all five months, with nothing adjusted in between.
The shovel is never near full — it stays between 42 and 63 percent. Every month.
The driving share stays between 35 and 43 percent. Every month.
And first place is a tie in all five months. Nothing clears the margin anywhere, so "there is no single winner" is not a November accident either.
Second, there are a few numbers in the method that we chose rather than derived.
For example, we call a truck stopped when its speed is 2 km an hour or less. That is our choice.
So we checked it against the odometer, which is a completely separate sensor from the GPS position.
Over all the time we labelled "stopped", the odometer moved at 0.3 km an hour. Essentially not moving.
Over the time we labelled "driving", 35 km an hour. So the two sensors agree.
The other rule worth checking is where we draw the line between a station and a place trucks just drive past.
We do not have to choose carefully, because the data leaves a gap: places on the route either have trucks stopping almost every time, 0.89 and up, or almost never, 0.20 and down. Nothing sits in between, so any threshold in that gap gives the same answer.
One number we deliberately do not report at all is the theoretical maximum output. It moves too much under plausible choices to be worth quoting.

**中.** 我们做了两件事来自检。

**第一，同一套代码跑了全部五个月，中间什么都没调。** 铲车从来不接近满负荷，始终在 **42% 到 63%** 之间，每个月都是。行驶占比始终在 **35% 到 43%**。**而且五个月的第一名全部是并列**——没有哪个月有杠杆能拉开差距，所以"没有单一第一名"也不是十一月的偶然。

**第二，方法里有几个数字是我们选的，不是推出来的。** 比如我们规定速度 ≤2 km/h 算"停着"，**这是我们选的**。

**所以我们拿里程表来验**——那是跟 GPS 位置完全无关的另一个传感器。**在我们标为"停着"的全部时间里，里程表的平均速度是 0.3 km/h，基本没动。在标为"在开"的时间里是 35 km/h。两个传感器互相印证。**

另一条值得验的规则是**站点和"只是开过去的地方"之间那条线画在哪**。**我们其实不用小心地挑**，因为数据本身留了空档：路线上的地方要么几乎每次都停（0.89 以上），要么几乎从不停（0.20 以下），**中间是空的**，所以那条线画在空档里的任何位置，结果都一样。

**有一个数我们刻意完全不报：理论最大产量。** 它在合理的参数范围内晃得太厉害，不值得引用。

---

## 12 ｜ 不能声称的，和跟论文的关系 What we cannot claim, and how this relates to the paper

**EN.**
A few limits I want to state clearly.
We can show that trucks stop at five fixed places on every trip, for a few minutes each, and that the wait grows when other trucks are there.
But we cannot verify what actually happens at those places. The names come from the mine's own map labels, and nobody has confirmed them.
So we say "trucks stop here for six minutes". We do not say "tarping takes six minutes".
Also, only 11 of the 104 zones have a real shape drawn. The rest are rectangles. That is why one item in our list has no name — trucks stopped somewhere with no zone around it.
There is no payload data, so everything is in loads, never tonnes.
And this is one flow, at one mine, over five months, with no winter.
Finally, this is a diagnosis. It is not proof. To prove a gain, you would have to change something and measure again.
On the paper. It uses the same data and the same overall idea, and it is also diagnostic.
A few things differ. The paper decides queue-versus-idle from how long a stop lasted and where it sat relative to a zone outline; here it is decided by whether another truck was already being served. The paper models two stations; here we find six.
And the paper gives one number, plus 53.8 percent, where we give a range.
But those two numbers answer different questions. The paper asks what happens if every trip hits the fastest baseline. We ask what happens if every day matches your own best day.
Ours is deliberately a floor. Neither number corrects the other.
One thing to be clear about, because it affects how you read the paper alongside this. The pipeline the paper describes works at the level of individual GPS points and already separates moving from stopped. Everything I have said about durations applies to the layer we built on top of it, not to that.
And that is the part I would keep if you forget everything else. Almost every quantity in a study like this is a duration, and almost every duration is two timestamps subtracted. That is the step to be suspicious of. It tells you when something started and when it ended, and nothing whatsoever about what happened in between — and at this mine, what happened in between is more than half the time. Everything in this talk follows from checking that.

**中.** 几条限制我想说清楚。

**我们能证明卡车每趟都在五个固定地点停留几分钟，而且有别的车在场时等待会变长。但我们无法验证那些地方实际在干什么。** 名字来自矿方自己的地图标签，没人确认过。**所以我们说"卡车在这里停六分钟"，不说"盖篷布需要六分钟"。**

另外，**104 个区域里只有 11 个画了真实形状**，其余是长方形。**这就是为什么我们表里有一项没有名字**——卡车停在了一个没画区域的地方。

没有载重数据，所以单位永远是趟数不是吨。而且这是**一条物料流、一个矿、五个月、没有冬季**。

**最后，这是诊断，不是证明。要证明收益，得改点什么再测一次。**

关于论文。**它用同样的数据、同样的整体思路，也是诊断性的。** 有几处不同：论文按"停了多久"和"相对区域多边形停在哪"来判排队还是闲置，这里按"到达那一刻有没有别的车正在被服务"来判；论文建模两个站点，这里找到六个；论文给一个数 +53.8%，我们给区间。

**但这两个数回答的是不同的问题。** 论文问"如果每趟都达到最快那批会怎样"，我们问"如果每天都做到你自己最好的那天会怎样"。**我们的是刻意取的下界。谁也不是在纠正谁。**

**有一点要说清楚，因为它关系到你怎么把论文和这份材料放在一起读。** 论文描述的那套流程是在单个 GPS 点的层面工作的，**本来就区分移动和静止**。我讲的所有关于"时长"的事，针对的是我们加在它上面那一层，不是它。

**而这一条，如果别的都忘了，我希望留下。** 这类研究里几乎每个量都是"时长"，而几乎每个时长都是两个时间戳相减。**那一步才是该起疑的地方。** 它告诉你什么时候开始、什么时候结束，**完全不告诉你中间发生了什么**——而在这个矿，中间发生的事占了一半以上的时间。**这次讲的所有内容，都是从核对这一件事开始的。**

---

## 13 ｜ 下一步 What comes next

**EN.**
Three things, in the order we would do them.
First, the item sitting at joint first — trucks standing still in places nobody has drawn a zone around, 770 truck-hours. Right now that is not a recommendation, it is an admission. My collaborator's pipeline already clusters stop positions by density, without needing a zone to exist, so the locations are recoverable from data we already have. Once we have them, each one either becomes a real recommendation — "trucks lose an hour a day at this spot, go and look at what is there" — or it leaves the ranking because it turns out to be a repair yard, which is not a dispatch problem at all.
Second, the layer that writes the brief. It runs on a language model, and we are moving it to GPT-4o so it matches the rest of the project. The model is given only the diagnosis and told to invent nothing.
Third, this whole diagnosis becomes one more specialist inside the question-answering agent, so "what should we do about it" sits next to "how much idle do we have" and gets answered from the same place.

**中.** 三件事，按会做的顺序。

**第一，把并列第一那项定位出来。** 卡车停在没人画过区域的地方，770 卡车小时——**它现在不是一条建议，是一句"我们不知道"**。Uranbileg 那套流程已经在按密度聚类停车位置，**不需要事先存在一个区域**，所以位置从我们手上已有的数据里就能还原。

拿到之后，每个点要么变成一条真建议——**"车每天在这个位置损失一小时，去看看那儿是什么"**，比如路况有问题就该去查；要么它离开排序，因为查出来是维修厂，那根本不是调度的事。

**第二，写简报那一层换成 GPT-4o**，跟项目其余部分统一。模型只拿到诊断结果，明确要求不许编。

**第三，把这套诊断做成她那个问答 agent 里的一个专家**，这样"我们该怎么办"和"我们有多少闲置"就在同一个地方回答。

---

## 备用 · 被问到再答 If asked

**Q: 为什么是 2 km/h？为什么是 30 分钟？**
**EN.** Both are chosen, not derived. The 2 km/h one we checked against the odometer, which is a separate sensor: time we call stopped shows 0.3 km/h, time we call driving shows 35.4. The 30-minute one has not been re-swept since the cycle construction changed, so I would not claim more for it than that.
**中.** 都是选的不是推的。2 km/h 那个拿里程表验过——那是另一个传感器：我们标为"停着"的时间里程表走 0.3 km/h，标为"在开"的走 35.4。30 分钟那个在周期构建改动之后没有重扫过，所以我不会替它多声称什么。

**Q: 一趟车是怎么切出来的？有什么坑？**
**EN.** Two rules that matter more than they look. A truck only counts as having arrived at the load zone if it actually stopped — 41 percent of the times a truck is inside that zone it is there for under a minute, driving past the corner, and counting those closes trips that never happened. And we never discard a trip for taking too long: eleven hours is either a truck that stood somewhere or a tracker that was switched off, and the duration cannot tell you which, so we keep it and record the longest gap in its GPS instead.
**中.** 两条规则比看上去重要。**车必须真的停下来**才算到达装车区——车在装车区里的时候有 **41% 的次数待不满一分钟**，那是从边角开过去，算进来就会"结束"一趟不存在的行程。**不因为跑得久就扔掉一趟**——十一小时可能是车停着，也可能是设备关了，**时长本身分不出来**，所以保留它，另外记下 GPS 的最大空洞。

**Q: 这些项能加起来吗？**
**EN.** No. Each one assumes the others stay. Fixing them all at once gives more than the sum, not less.
**中.** 不能。每项都假设别的不变。全部一起修比相加还多，不是更少。

**Q: 换个矿能用吗？**
**EN.** The step that finds the places reads no names — only how often trucks pass and whether they stop. So in principle yes. But we have only tested one flow.
**中.** 找地点那一步不读名字，只看经过频率和停不停，所以原则上可以。但我们只测过一条流。

**Q: 那 770 小时"不知道在哪"的停留是什么？**
**EN.** Trucks stopped somewhere the mine has not drawn a zone around. 93 of the 104 zones have no real shape. It is now joint first on the list, at 770 truck-hours, and we would need access to the zone system to resolve it.
**中.** 卡车停在了矿方没画区域的地方。104 个区域里 93 个没有真实形状。**现在它并列第一，770 卡车小时**，要解决得有区域系统的访问权限。

**Q: 为什么你们的数字比论文低？**
**EN.** Different question. Ours is a floor with a real day behind it. Theirs is what happens if every trip is perfect.
**中.** 问的问题不同。我们的是下界，背后有真实发生过的一天。他们的是"每趟都完美会怎样"。
