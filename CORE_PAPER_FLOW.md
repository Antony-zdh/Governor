这里记录论文的核心写作逻辑流

1. 我们发现False Consensus

Vanilla Consensus准确率低，即有较大的false stop rate，命名为false consensus。这直接推翻了一个假设：agreement=correctness。Consensus不但容易出错，而且也不terminal。Consensus的答案与推理最终答案经常不同，且在这些不同中，Recovery:Overthinking约为35:1，即Consensus截断了大量可能的recovery。

2. 是否有一种策略可以很好地利用consensus信号，并稳定实现{准确率几乎不掉}+{省大量tokens}呢？

3. Pareto Sweep

在preregistered的策略空间中没有找到满足能够稳定{准确率几乎不掉}+{省大量tokens}的策略。即在train中得到候选，却在dev上集体未达标。

4. 那么{准确率几乎不掉}+{省大量tokens}的Early Exit是不是不可能呢？

不是的。Early Exit是可能的，DEER可以实现稳定的{准确率几乎不掉}+{省大量tokens}。说明只是Consensus信号不行。

具体证明：在同样的Pareto sweep设置中成功通过train+dev得到策略，并在test上证实泛化。（对比consensus未通过train+dev）
辅助证明：在benchmark、model size、architecture、model family上都具有泛化性。（对比consensus的泛化结果）

5. Consensus信号不行的机制解释

首先数据上，Certaindex论文中提到的consensus=terminality不成立，我们发现35:1的recovery-overthinking比值。因此相对于vanilla基线大量掉准确率。

其次对具体早停的分析上，我们发现Consensus早停存在大量临时猜测/Placeholder，停止时并不是思考收敛到了某个答案。这里可以引用人工标注的早停原因来解释。

更深层次但尚未实验确认的分析：
    Consensus基于的periodic probing实际上是在强制模型输出一个临时答案，probing本身并不反映模型自身对答案的自信程度。理想中的consensus信号应该是：模型在思考过程中发现了很可能正确的答案后，后续的检查/继续思考继续佐证/不反对这个答案的最可能正确性，因此在k次agreement后可以早停。但是实际上：模型提交的答案未必是它认为很可能正确的答案，而经常是临时的猜测或甚至是placeholder，而当后续的思考没有发现模型认为真正可能正确的答案之前，它连续地输出这个猜测/placeholder，但consensus机制认为此时模型已较为确定，因而输出了这个猜测/placeholder。这是一个系统性的风险，而我们观测到的长window提升准确率的一个原因是：模型提交猜测/placeholder后，有更长的缓冲空间，以让模型找到真正值得信任的答案，或证伪之前的猜测/placeholder，因而大幅减少了false consensus。但即使长window减少了false consensus，系统性风险仍然没有被消除。一个analogy是，一个家长不断询问孩子对什么感兴趣，并强制孩子回答，而孩子此时没有真正想好自己的兴趣爱好，就只能回答一个猜测/placeholder，而家长错误地认为这就是孩子真正的兴趣，并给孩子报了兴趣班。换句话说，早停信号如果屏蔽了模型真正的估计，会造成系统性的false consensus。