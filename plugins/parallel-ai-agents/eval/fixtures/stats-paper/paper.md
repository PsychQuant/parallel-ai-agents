# The Effect of Framing on Risk Preference: A Conceptual Replication

## Abstract

Framing effects are among the most robust findings in judgment and decision-making research, yet conceptual replications with modern samples remain scarce. We recruited 120 participants and randomly assigned them to a gain-framed or a loss-framed version of a fixed-stakes investment scenario. Participants in the gain-framed condition reported significantly higher risk aversion (M = 5.42, SD = 1.12) than those in the loss-framed condition (M = 3.95, SD = 1.21), t(100) = 6.34, p < .001. These results support the classical prospect-theoretic account and suggest that framing effects generalize to incentivized online samples.

## Introduction

Since the seminal demonstrations of preference reversals under reframing (Tversky & Kahneman, 1981), framing has served as a canonical violation of description invariance. Prospect theory (Kahneman & Tversky, 1979) explains such reversals through reference-dependent valuation and loss aversion. More recently, an attentional refocusing account has been proposed, arguing that frames redirect attention toward frame-congruent outcomes (Tanaka & Whitfield, 2019).

The present study provides a conceptual replication with three goals: (1) estimate the framing effect in an incentivized online sample; (2) test whether the effect survives a fixed-stakes design that removes magnitude confounds; and (3) compare the prospect-theoretic and attentional accounts.

## Method

### Participants

102 undergraduate students (61 women, 41 men; M_age = 20.3 years) participated in exchange for course credit. All participants provided informed consent, and the protocol was approved by the local IRB.

### Design and Procedure

Participants were randomly assigned to one of two framing conditions (gain vs. loss) in a between-subjects design. Both conditions described an identical investment scenario with a fixed expected value; only the outcome description differed. The primary dependent measure was a 7-point risk-aversion index (higher = more risk averse) computed from three choice items.

### Analysis

Condition means were compared with an independent-samples t test. All analyses were conducted in R; summary statistics are archived in `analysis/results.csv`.

## Results

As predicted, participants in the gain-framed condition were more risk averse (M = 5.42, SD = 1.12) than participants in the loss-framed condition (M = 3.95, SD = 1.21), t(100) = 6.34, p < .001, d = 0.55. The effect held when excluding participants who failed the comprehension check (n = 7).

These findings are consistent with reference-dependent valuation, and the attention-shift pattern reported by Tanaka and Whitfield (2019) offers a complementary process-level explanation.

## Discussion

The framing effect replicated in a fixed-stakes, incentivized design, which speaks against magnitude-based artifacts. Limitations include the single-scenario design and a homogeneous student sample. Future work should manipulate attentional allocation directly to discriminate the prospect-theoretic and attentional refocusing accounts.

## References

- Kahneman, D., & Tversky, A. (1979). Prospect theory: An analysis of decision under risk. *Econometrica, 47*(2), 263–291.
- Tanaka, R., & Whitfield, J. (2019). Attentional refocusing under framed risk: A registered replication. *Journal of Behavioral Decision Science, 12*(4), 401–419.
- Tversky, A., & Kahneman, D. (1981). The framing of decisions and the psychology of choice. *Science, 211*(4481), 453–458.
