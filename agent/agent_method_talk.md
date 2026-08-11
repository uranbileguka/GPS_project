# Talking script ｜ 讲稿

**配合 `agent_method_EN.md` 使用。** 文档里的细节比这份多——**讲的时候只讲这 13 节，剩下的留给对方自己看或者提问时再展开。**

**中文是对照**，用来确认自己讲到哪。约 **18 分钟**。

**砍掉不讲的**（文档里有，讲的时候跳过）：卡车和区域怎么识别、作业小时的 0.4、站点速率的算法细节、站点时间三分、报告前的第 3 和第 4 条规则。这些被问到再说。

---

## 1 ｜ 这是什么 What this is

**EN.**
We have GPS from the haul trucks. That is all we have.
No payload data, no fuel data, no dispatch records.
From that, we want to answer one question: where does this fleet lose time?
And not just where. We also want to rank it — what is worth the most to fix.
The output is a list. Each item says how many extra loads per day you would get.
I will go through how we get from raw GPS to that list.

**中.** 我们有卡车的 GPS，就只有这个。没有载重、没有油耗、没有调度记录。我们想回答一个问题：**这支车队的时间损失在哪。** 不只是"在哪"，还要排序——哪一项最值得改。**输出是一张表，每一项写着修好它每天能多拉几车。** 我讲一下从原始 GPS 怎么走到这张表。

---

## 2 ｜ 先把点位变成一趟车 From pings to trips

**EN.**
The GPS gives us a position every twelve seconds or so. Millions of points.
The first thing we do is turn that into trips.
The mine has drawn zones on the map — where trucks load, where they dump.
So we check every GPS point: is it inside a zone, or not?
Then we look at the sequence. A truck sits in the load zone. Then it moves. Then it sits in the dump zone. Then it comes back.
That is one trip. We call it a cycle.
For this one load zone in November, that gives 2 417 trips, from 22 trucks, over 30 days.

**中.** GPS 大约每 12 秒给一个位置，几百万个点。**第一件事是把它变成"一趟一趟的车"。** 矿方在地图上画了区域——哪里装车、哪里卸车。所以我们对每个点位问：它在不在某个区域里？然后看顺序：一台车待在装车区，然后移动，然后待在卸点，然后回来。**这就是一趟。** 这一个装车区，十一月，得到 **2417 趟，22 台车，30 天**。

---

## 3 ｜ 一趟车分成四段 The four parts of a trip

**EN.**
Each trip has four parts, and we know the exact time of each boundary.
The truck leaves the load zone. That starts the loaded haul.
It arrives at the dump. That is the dump phase.
It leaves the dump. That is the empty return.
It arrives back at the load zone. And then it sits there until it leaves again — that is the dwell.
On average at this mine: haul 75 minutes, dump 19, return 88, and dwell 50.
The dwell is important. It covers the loading itself, plus any time the truck spends waiting to be loaded.

**中.** 每趟分四段，而且每个边界的时刻我们都有。车离开装车区——重载去程开始。到达卸点——卸车段。离开卸点——空车回程。回到装车区——然后待在那儿直到再次出发，这段叫**停留**。这个矿的均值：去程 75 分钟、卸车 19、回程 88、停留 50。**停留这一段很重要，它包含装车本身，也包含等着被装的时间。**

---

## 4 ｜ ⭐ 但"用了多久"不等于"开了多久" The problem with those durations

**EN.**
Now here is the thing that took us a while to notice.
Look at that return phase: 88 minutes on average. It is tempting to say the road is slow.
But that 88 minutes is just two timestamps subtracted. When the truck left the dump, and when it got back.
It tells you nothing about what happened in between.
Let me show you one real trip. Truck 34065, on the third of November.
It left the dump at 17:17 and got back at 20:28. So 191 minutes.
But when we look at the GPS second by second: it drove for 12 minutes.
Then it sat at a car park for 105 minutes.
Then it drove for 47 minutes.
Then it sat at the gate into the pit for 26 minutes.
Then it drove the last 2 minutes.
So: 61 minutes of driving. 130 minutes of standing still.
And that 105-minute stop is not an accident. It is the six o'clock shift change.
Across the whole month, only 56 percent of that so-called road time is a truck actually driving.
So before we can say anything about delay, we have to find out where that other 44 percent goes.

**中.** 有一件事我们花了一阵才注意到。看那个回程：平均 88 分钟，很容易就说"路慢"。**但这 88 分钟只是两个时间戳相减**——车什么时候离开卸点、什么时候回来。**它完全不告诉你中间发生了什么。**

举一趟真的。34065 号车，11 月 3 日。17:17 离开卸点，20:28 回来，191 分钟。但把 GPS 一秒一秒看下去：开了 12 分钟，**在停车场坐了 105 分钟**，又开 47 分钟，**在采场门口停了 26 分钟**，最后开 2 分钟。

**开车 61 分钟，停着 130 分钟。** 而那 105 分钟的停留不是意外——**那是傍晚六点的换班**。

整月看，所谓"路上时间"里只有 **56%** 是卡车真在开车。**所以在谈延误之前，得先搞清楚剩下的 44% 去了哪。**

---

## 5 ｜ 那条路上到底有什么 What is actually on that road

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
And some are not on every trip at all. The car park is the big one. Only 16 percent of trips go there. But when they do, they sit for 40 minutes.
That last group has to be taken out of the loop entirely, and I will explain why on the next point.

**中.** 矿方在地图上画了 **104 个区域**，不只是装车区和卸点——还有过磅站、停车场、路口等等。**但我们不知道它们是干什么用的**：问不到现场，名字又是蒙文。

所以我们不猜，而是**对这 104 个地方，向 GPS 问两个问题**。

**第一：是不是每趟都经过？** 数一下卡车访问了多少次，除以总趟数。如果一个地方在路线上，去程回程各过一次，就是约 200%。

**第二：车是真停下来了，还是只是开过去？** 看速度有没有降到接近零。

这两个问题把 104 个地方分成三组：**每趟都过、而且车会停**——五个：两个过磅站、两个盖篷布点、进采场的门口。**每趟都过、但没人停**——路口、转弯，那就是路上的点而已。**还有一些根本不是每趟都去**——停车场是最大的一个，只有 16% 的趟数会去，但一去就坐 40 分钟。**最后这一组必须整个移出循环**，下一节说为什么。

---

## 6 ｜ ⭐ 延误是跟什么比出来的 What "delay" is measured against

**EN.**
Now, how do we decide that some time was wasted?
We never compare against a manufacturer's number, or a target somebody set.
We compare each truck against what this same fleet does when nothing is in the way.
For driving on the road: we take the fastest 15 percent of trips, and use that as the free-flow time.
But — and this is the point of the last section — we only count time when the truck was actually moving. Not the parked time.
For loading: we take the fastest 20 percent of the load-zone dwells. That is what loading takes with no queue. About 16 minutes here.
For a weighbridge or a tarping point: we do something better than a percentile.
We look at all the visits where no other truck was there. The median of those is the service time. That is measured directly, not chosen.
Now back to the car park.
The reference for the road comes from the fastest trips. And the fastest trips do not stop at the car park.
So if we leave the car park inside the road, that whole 40-minute shift change gets counted as road delay.
And the recommendation would come out as "fix the road" — when what actually happened is a shift change.
That is why anything that is not on every trip has to come out.

**中.** 那我们怎么判断某段时间是浪费的？**我们从不跟厂家参数比，也不跟谁定的目标比。我们拿每台车跟"这支车队自己在没有阻碍时的表现"比。**

**路上行驶**：取最快的 15% 的趟数，当作自由流时间。**但是**——这就是上一节的意义——**我们只算车真的在动的那部分时间，不算停着的**。

**装车**：取最快的 20% 的停留，那就是"没有排队时装车要多久"，这里大约 16 分钟。

**过磅站或盖篷布点**：这里我们用了比分位数更好的办法。**看所有"没有别的车在场"的访问，取它们的中位时长，那就是服务时间。** 这是直接量出来的，不是挑的。

再回到停车场。**路的参照来自最快的那批趟，而最快的那批趟不会去停车场。** 所以如果把停车场留在"路"里面，**那整整 40 分钟的换班会被算成路上延误**，建议就会变成"去修路"——而实际发生的是换班。**这就是为什么不是每趟都有的东西必须拿出去。**

---

## 7 ｜ ⭐ 怎么分清"排队"和"装车就是慢" Telling a queue from slow loading

**EN.**
At the load zone, the dwell mixes several different things, and we want to separate them.
The obvious way would be by duration — long waits are queues, short waits are loading.
But that does not work. Let me show you two real cases.
One truck sat at the load zone for 20 minutes. Another sat for 46.
By duration you would call the second one a queue.
But here is what actually matters. When the first truck arrived, there was nobody else there.
So those 20 minutes are simply how long loading took that time. That is not a delay.
When the second truck arrived, there were already four trucks in front of it.
That is a queue. Those 46 minutes include real waiting.
So the test we use is not how long the truck waited. It is how many trucks were already there when it arrived.
Same for the weighbridges and the tarping points. If nobody else was there, it is service time. If someone was, the extra is a queue.
And we can check this. If it really is a queue, then more trucks present should mean longer waits.
It does. With nobody there, the median stop is under 3 minutes. With four trucks there, it is over 6.

**中.** 装车区的停留混着好几种东西，我们想把它们分开。**最直觉的办法是按时长分**——等得久就是排队，等得短就是装车。**但这行不通。** 看两个真实的例子。

一台车在装车区待了 **20 分钟**，另一台待了 **46 分钟**。按时长判，你会说第二个是排队。

**但真正起作用的是这个：第一台车到的时候，周围一台车都没有。** 所以那 20 分钟就是这次装车花了这么久，**不是延误**。**第二台车到的时候，前面已经排着四台。** 那是排队，那 46 分钟里含着真实的等待。

**所以我们的判据不是等了多久，是到达那一刻前面有几台车。** 过磅站和盖篷布点同理：没有别的车在场就是服务时间，有车在场时多出来的就是排队。

**而且这可以验证。** 如果真是排队，那在场的车越多，等得应该越久。**确实如此**：没车的时候中位不到 3 分钟，有四台车的时候超过 6 分钟。

---

## 8 ｜ 铲车是不是瓶颈 Is the shovel the limit?

**EN.**
There is an obvious question here. Maybe there is a queue because the shovel simply cannot load fast enough.
So we measured that. We looked at how quickly trucks leave the load zone when the shovel is busy.
The answer is about one truck every 8 minutes. So roughly 7 trucks an hour.
And how many is it actually doing? About 3.7 an hour.
So the shovel is working about half the time. It is idle for the other half.
That is the interesting part. There is a queue in front of it, and it is idle half the time.
Those two things together mean one thing: the trucks are not arriving evenly.
They come in bunches. The shovel is swamped, then it waits, then it is swamped again.
So a bigger shovel would not help. The problem is the timing of arrivals.

**中.** 这里有个明显的问题：**会不会就是因为铲车装不过来，所以才排队？**

所以我们量了一下：铲车忙的时候，卡车多久离开一次装车区。答案是**大约每 8 分钟一台，也就是每小时约 7 台**。那它实际在做多少？**每小时约 3.7 台**。

**所以铲车大概有一半时间在干活，另一半闲着。**

**这才是有意思的地方：它前面排着队，而它有一半时间是闲的。** 这两件事放一起只说明一件事——**卡车到得不均匀**。它们成堆地来，铲车被淹一阵，然后等一阵，然后又被淹。

**所以换个更大的铲车没有用，问题在到达的时间分布。**

---

## 9 ｜ 把小时换成"每天几车" Turning hours into loads per day

**EN.**
Now we have delays, but they are in truck-hours. That is hard to compare across different causes.
So we convert everything into the same unit: extra loads per day.
The logic is simple. This fleet puts 312 truck-hours into the loop every day.
One full loop currently takes 232 minutes. That works out to 80.6 loads a day.
Now suppose we remove the queue at the load zone. The loop drops to 198 minutes.
Same 312 hours, shorter loop — so 94.5 loads a day.
That is 14 more loads, from that one fix.
We do this for every cause, and then we rank them.
One warning about the ranking. You cannot add these numbers up.
Each one assumes the others stay as they are. If you fixed everything at once you would get more than the sum, not less.
So we use the list to decide what to do first. Not to promise a total.

**中.** 现在我们有了延误，但单位是卡车小时，不同原因之间没法比。**所以全部换成同一个单位：每天多几车。**

逻辑很简单。这支车队每天往循环里投 **312 卡车小时**。现在跑一圈要 232 分钟，算下来是 **80.6 车/天**。

假设我们去掉装车区的排队，一圈变成 198 分钟。**同样的 312 小时，圈短了，就是 94.5 车/天。** 也就是**这一项值 14 车/天**。

每个原因都这么算一遍，然后排序。

**关于排序有一个提醒：这些数字不能相加。** 每一项都假设别的不变。如果全部一起修，得到的会**比相加还多**，不是更少。**所以这张表是用来决定先做什么的，不是用来承诺一个总数的。**

---

## 10 ｜ 结果 The result

**EN.**
For November, at this load zone, here is the ranking.
Queue at the load zone comes first. Worth about 14 loads a day.
The dump is second, worth about 6.
Then the stations near the dump, worth about 5.
And the two road items — the actual driving — come seventh and eighth. Worth 2 and 1.6.
So the road is not the problem here. Once you take the parked time out of it, the driving is efficient.
In fact, empty trucks drive faster than loaded ones, which is what you would expect physically.
Before we showed the fix, they looked slower. That was the parked time.
One more thing about the ranking. There are two items we deliberately keep out of it.
Overnight parking is worth 42 loads a day on paper. That is bigger than everything else combined.
But no dispatcher can recover it. You would have to add a shift.
Same with the shift change. So we report both, but separately, because they go to a different person.

**中.** 十一月，这个装车区，排序是这样。

**装车区排队第一，约 14 车/天。** 卸点第二，约 6。然后是卸点附近的站点，约 5。**而两条路——真正的行驶——排第七和第八，值 2 和 1.6。**

**所以路在这里不是问题。** 把停着的时间拿掉之后，行驶是高效的。**实际上空车比重载开得快**，这才符合物理常识。**在我们修正之前，空车看起来更慢——那是停车时间造成的。**

关于排序还有一点。**有两项我们刻意不放进去。** 过夜停放纸面上值 42 车/天，比其他所有加起来还大。**但没有调度员能回收它，那得增加班次。** 换班交接同理。**所以两项都报，但单独报，因为它们是给另一个人看的。**

---

## 11 ｜ 能提升多少 How much is recoverable

**EN.**
Naturally the next question is: how much is all this worth in total?
We give two numbers, not one, because we cannot honestly give a single one.
The lower one is plus 21 percent. Here is what that means.
We took every normal working day in November and found the best one.
If every normal day matched that best day, output would be 21 percent higher.
That number has something behind it — that day actually happened. So we know it is achievable.
About half of it comes from having more trucks out on the day, which is a maintenance question.
The other half comes from each truck doing more trips. That is the half that depends on how they are dispatched.
The higher number is plus 75 percent. That is if every delay we identified disappeared at once.
That has never happened, and it never will. We report it as an upper limit, not as a target.
Separately from all this: four days in November were near-shutdowns. Those four days cost 12 percent of the month's output.
That is bigger than any of our items. But it is a maintenance or weather problem, not a dispatch one.

**中.** 接下来自然的问题是：**这些加起来值多少？** 我们给**两个数，不是一个**，因为诚实地说给不出一个。

**低的那个是 +21%。** 意思是：我们把十一月所有正常工作日拿出来，找出最好的那一天。**如果每个正常日都做到那一天的水平，产量就高 21%。** 这个数是有依据的——**那一天真的发生过，所以我们知道它能做到。**

其中大约一半来自那天出勤的车更多，**那是维修的问题**。另一半来自每台车多跑了几趟，**那一半才取决于怎么调度**。

**高的那个是 +75%**，意思是我们找出的所有延误一次全部消失。**那从没发生过，也不会发生。我们把它当上限报，不是当目标。**

另外单独说一件事：**十一月有四天几乎停产，那四天占掉了全月产量的 12%。** 比我们任何一项都大，**但那是维修或天气的问题，不是调度的**。

---

## 12 ｜ 这些结论稳不稳 How much of this holds up

**EN.**
Two things we did to check ourselves.
First, the same code on all five months, with nothing adjusted in between.
The shovel is never near full — it stays between 43 and 59 percent. Every month.
The driving share stays between 56 and 58 percent. Every month.
And the empty return road is seventh or eighth every month. So that correction is not a one-month accident.
Second, there are a few numbers in the method that we chose rather than derived.
For example, we call a truck stopped when its speed is 2 km an hour or less. That is our choice.
So we checked it against the odometer, which is a completely separate sensor from the GPS position.
Over all the time we labelled "stopped", the odometer moved at 0.3 km an hour. Essentially not moving.
Over the time we labelled "driving", 35 km an hour. So the two sensors agree.
We did the same kind of test for the other chosen numbers — 175 different combinations.
The ranking did not change. The shovel was never full in any of them.
One thing did move a lot: the theoretical maximum output, which swung from 125 to 273 loads a day.
So we stopped reporting that number at all.

**中.** 我们做了两件事来自检。

**第一，同一套代码跑了全部五个月，中间什么都没调。** 铲车从来不接近满负荷，始终在 43% 到 59% 之间，每个月都是。行驶占比始终在 56% 到 58%，每个月都是。**空车回程路每个月都排第七或第八**——所以那个修正不是某一个月的偶然。

**第二，方法里有几个数字是我们选的，不是推出来的。** 比如我们规定速度 ≤2 km/h 算"停着"，**这是我们选的**。

**所以我们拿里程表来验**——那是跟 GPS 位置完全无关的另一个传感器。**在我们标为"停着"的全部时间里，里程表的平均速度是 0.3 km/h，基本没动。在标为"在开"的时间里是 35 km/h。两个传感器互相印证。**

其他选定的数字也做了同类测试，一共 **175 种组合**。**排序没有变，铲车在任何一种组合下都没有满过。**

**有一样确实晃得厉害：理论最大产量，从 125 到 273 车/天。所以那个数我们干脆就不报了。**

---

## 13 ｜ 不能声称的，和跟论文的关系 What we cannot claim, and how this relates to the paper

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
A few things differ. The paper fixes the dwell boundary at 120 minutes; here it is learned from the data. The paper models two stations; here we find six.
And the paper gives one number, plus 53.8 percent, where we give a range.
But those two numbers answer different questions. The paper asks what happens if every trip hits the fastest baseline. We ask what happens if every day matches your own best day.
Ours is deliberately a floor. Neither number corrects the other.
One last thing I want to be clear about. The problem I showed you earlier — the parked time counted as road time — that is ours, not the paper's. The paper works at the individual GPS point level and already separates moving from stopped.

**中.** 几条限制我想说清楚。

**我们能证明卡车每趟都在五个固定地点停留几分钟，而且有别的车在场时等待会变长。但我们无法验证那些地方实际在干什么。** 名字来自矿方自己的地图标签，没人确认过。**所以我们说"卡车在这里停六分钟"，不说"盖篷布需要六分钟"。**

另外，**104 个区域里只有 11 个画了真实形状**，其余是长方形。**这就是为什么我们表里有一项没有名字**——卡车停在了一个没画区域的地方。

没有载重数据，所以单位永远是趟数不是吨。而且这是**一条物料流、一个矿、五个月、没有冬季**。

**最后，这是诊断，不是证明。要证明收益，得改点什么再测一次。**

关于论文。**它用同样的数据、同样的整体思路，也是诊断性的。** 有几处不同：论文把停留分界线固定在 120 分钟，这里是从数据学出来的；论文建模两个站点，这里找到六个；论文给一个数 +53.8%，我们给区间。

**但这两个数回答的是不同的问题。** 论文问"如果每趟都达到最快那批会怎样"，我们问"如果每天都做到你自己最好的那天会怎样"。**我们的是刻意取的下界。谁也不是在纠正谁。**

**最后一点我想说明白：我前面讲的那个问题——把停车时间算成路上时间——那是我们的问题，不是论文的。** 论文是在单个 GPS 点的层面工作的，**本来就区分了移动和静止**。

---

## 备用 · 被问到再答 If asked

**Q: 为什么是 2 km/h？为什么是 30 分钟？**
**EN.** Both are chosen, not derived. We tested 175 combinations of them. The ranking never changed, and the shovel was never full in any of them.
**中.** 都是选的不是推的。测了 175 种组合，排序从没变过，铲车在任何组合下都没满过。

**Q: 八项能加起来吗？**
**EN.** No. Each one assumes the others stay. Fixing them all at once gives more than the sum, not less.
**中.** 不能。每项都假设别的不变。全部一起修比相加还多，不是更少。

**Q: 换个矿能用吗？**
**EN.** The step that finds the places reads no names — only how often trucks pass and whether they stop. So in principle yes. But we have only tested one flow.
**中.** 找地点那一步不读名字，只看经过频率和停不停，所以原则上可以。但我们只测过一条流。

**Q: 那 405 小时"不知道在哪"的停留是什么？**
**EN.** Trucks stopped somewhere the mine has not drawn a zone around. 93 of the 104 zones have no real shape. We would need access to the zone system to fix it.
**中.** 卡车停在了矿方没画区域的地方。104 个区域里 93 个没有真实形状。要解决得有区域系统的访问权限。

**Q: 为什么你们的数字比论文低？**
**EN.** Different question. Ours is a floor with a real day behind it. Theirs is what happens if every trip is perfect.
**中.** 问的问题不同。我们的是下界，背后有真实发生过的一天。他们的是"每趟都完美会怎样"。
