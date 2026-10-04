# Reference values for tests/test_datalab_engine.py (decision 2026-10-03: every method is checked
# against R). Run with `Rscript tests/fixtures/datalab_reference.R` and compare with the constants in
# the test; the datasets are R's own (sleep, mtcars) and the examples in R's help pages.

t <- t.test(extra ~ group, data = sleep)                      # Welch, the default
print(c(t$statistic, t$parameter, t$p.value, t$conf.int))      # -1.8608 17.776 0.07939 -3.3654832 0.2054832

w <- suppressWarnings(wilcox.test(extra ~ group, data = sleep)) # ties: normal approximation, continuity correction
print(c(w$statistic, w$p.value))                               # 25.5 0.06933

one <- t.test(sleep$extra)
print(c(mean(sleep$extra), one$conf.int))                      # 1.54 0.5955845 2.4844155

p <- cor.test(mtcars$mpg, mtcars$wt)
print(c(p$estimate, p$p.value, p$conf.int))                    # -0.8676594 1.294e-10 -0.9338264 -0.7440872

s <- suppressWarnings(cor.test(mtcars$mpg, mtcars$wt, method = "spearman", exact = FALSE))
print(c(s$estimate, s$p.value))                                # -0.886422 1.488e-11

M <- as.table(rbind(c(762, 327, 468), c(484, 239, 477)))      # ?chisq.test
x <- chisq.test(M)
print(c(x$statistic, x$parameter, x$p.value))                  # 30.07015 2 2.953589e-07

tea <- matrix(c(3, 1, 1, 3), nrow = 2)                         # ?fisher.test, TeaTasting
print(fisher.test(tea)$p.value)                                # 0.4857143

print(prop.test(15, 50, correct = FALSE)$conf.int)             # Wilson score interval
