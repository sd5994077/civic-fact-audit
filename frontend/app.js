const issues = [
  {
    title: "2020 election certification",
    stamp: "Congressional record available",
    summary:
      "One candidate treats certification as a lawful constitutional process and the January 6 attack as a criminal act. The other continues to frame the 2020 result through fraud rhetoric that was repeatedly rejected in court and not established by the record.",
    claimReview:
      '"The 2020 election was stolen and serious fraud justified blocking certification."',
    realStance:
      "Candidate B has repeatedly supported post-election fraud framing and objected to certification logic, while Candidate A has defended certification and legal process.",
    recordShows:
      "Courts, state officials, and post-election reviews did not establish outcome-changing fraud that would justify the claim.",
    aClaim:
      '"Election certification follows the law, and violent attempts to stop it were criminal."',
    aVerdict:
      "Supported by certification records, court outcomes, and January 6 prosecutions.",
    bClaim:
      '"Fraud justified blocking certification and the process was fundamentally illegitimate."',
    bVerdict:
      "Contradicted by court rulings, state certifications, and lack of substantiating evidence.",
    diff:
      "The difference is not stylistic. One candidate's framing tracks the legal and institutional record. The other relies on a fraud narrative that the evidentiary record does not sustain.",
    impact:
      "This changes how voters understand democratic legitimacy, willingness to accept certified results, and whether a candidate continues to amplify claims the record does not support.",
    primaryTitle: "Court rulings and state certification records",
    primaryNote:
      "Public filings and certification documents do not establish outcome-changing fraud.",
    secondaryTitle: "Congressional objections and January 6 case record",
    secondaryNote:
      "The record shows political objections and criminal prosecutions, not proof of a stolen election.",
    sources: [
      {
        type: "Texas Standard",
        typeClass: "source-type-primary",
        title: "Debate fact check: insurrection and election claims",
        summary:
          "Houston Public Media and the Texas Newsroom reviewed debate claims about insurrection, abortion, and candidate records.",
        url: "https://www.texasstandard.org/stories/cruz-allred-debate-fact-check-senate-texas/"
      },
      {
        type: "PolitiFact",
        typeClass: "source-type-secondary",
        title: "Ted Cruz and election-rigged rhetoric",
        summary:
          "This fact check examines Cruz's January 6, 2021 use of polling to support election-rigged claims and rates the statement misleading.",
        url: "https://www.politifact.com/factchecks/2021/jan/06/ted-cruz/ted-cruzs-misleading-statement-people-who-believe-/"
      },
      {
        type: "Texas Tribune",
        typeClass: "source-type-factcheck",
        title: "Debate coverage: abortion, immigration, and election rhetoric",
        summary:
          "Debate reporting captures how the candidates framed abortion, immigration, and January 6 during the 2024 race.",
        url: "https://www.texastribune.org/2024/10/15/texas-senate-debate-ted-cruz-colin-allred/"
      }
    ]
  },
  {
    title: "Border security and crossings",
    stamp: "Federal data available",
    summary:
      "Both candidates call for stronger border control, but they frame the problem differently. Candidate A emphasizes staffing, processing, and targeted enforcement. Candidate B often uses invasion rhetoric and broad crime claims that can outrun the public data.",
    claimReview:
      '"Texas is facing an invasion, and current policies prove the border is completely open."',
    realStance:
      "Candidate A supports bipartisan enforcement and asylum-processing reform. Candidate B favors harder detention and broader emergency framing.",
    recordShows:
      "Border encounters have been high, but the record does not support every sweeping crime or invasion claim attached to the issue.",
    aClaim:
      '"The border needs more agents, more judges, and a system that can process cases faster while still enforcing the law."',
    aVerdict:
      "Mostly supported. The claim matches operational and staffing problems documented by federal agencies.",
    bClaim:
      '"The border is effectively open, and Washington has allowed an invasion into Texas."',
    bVerdict:
      "Misleading to contradicted. Encounter data show strain, but the rhetoric exceeds what the cited crime and security evidence proves.",
    diff:
      "The real split is not whether border enforcement matters. It is whether the candidate describes the problem in operational terms or escalates it into a claim the record cannot fully support.",
    impact:
      "This matters because threat inflation can drive policy choices that are broader than the evidence justifies.",
    primaryTitle: "CBP encounter and staffing data",
    primaryNote:
      "Federal data confirm pressure on the system but do not, by themselves, prove every extreme rhetorical claim.",
    secondaryTitle: "Texas border reporting and public safety coverage",
    secondaryNote:
      "Independent reporting helps separate documented capacity issues from overgeneralized crime narratives.",
    sources: [
      {
        type: "CBP",
        typeClass: "source-type-primary",
        title: "Border encounters and enforcement statistics",
        summary:
          "Primary federal data provide the baseline for evaluating claims about crossings, encounters, and enforcement volume.",
        url: "https://www.cbp.gov/newsroom/stats"
      },
      {
        type: "Texas Tribune",
        typeClass: "source-type-secondary",
        title: "Debate coverage on the bipartisan border bill",
        summary:
          "Debate reporting documents Allred's attack on Cruz for helping take down a bipartisan border package earlier in 2024.",
        url: "https://www.texastribune.org/2024/10/15/texas-senate-debate-ted-cruz-colin-allred/"
      },
      {
        type: "Texas Standard",
        typeClass: "source-type-factcheck",
        title: "Debate fact check on immigration and public claims",
        summary:
          "Issue-by-issue debate fact checking is useful for separating border operations data from campaign framing.",
        url: "https://www.texasstandard.org/stories/cruz-allred-debate-fact-check-senate-texas/"
      }
    ]
  },
  {
    title: "Abortion and reproductive rights",
    stamp: "Voting record available",
    summary:
      "Candidate A says Texans should keep access to abortion and federal protections. Candidate B often frames the issue as state decision-making, but his record aligns with stronger abortion restrictions and opposition to federal abortion-rights protections.",
    claimReview:
      '"I just want states to decide, and I am not pushing a broader national abortion restriction."',
    realStance:
      "Candidate A supports abortion access protections. Candidate B's voting and advocacy record aligns with abortion restrictions and opposition to federal rights legislation.",
    recordShows:
      "Public voting records and statements matter more than softer campaign phrasing. The documented stance is more restrictive than a simple leave-it-to-the-states frame suggests.",
    aClaim:
      '"Texas women should not lose reproductive freedom because politicians want to control private medical decisions."',
    aVerdict:
      "Supported by the candidate's stated position and voting alignment on federal abortion-rights protections.",
    bClaim:
      '"This is about letting states decide, not imposing more federal restriction."',
    bVerdict:
      "Mixed. The framing softens a record that aligns with stronger abortion restrictions and opposition to federal abortion-rights bills.",
    diff:
      "The key distinction is between campaign phrasing and governing record. One candidate's claim matches the policy stance directly. The other uses narrower language than the record suggests.",
    impact:
      "Voters should be able to see not just the slogan, but whether the slogan accurately reflects the candidate's actual policy posture.",
    primaryTitle: "Congressional voting record on reproductive rights",
    primaryNote:
      "Votes and public statements provide a more reliable view of actual stance than softer campaign framing.",
    secondaryTitle: "Texas abortion law coverage and legal reporting",
    secondaryNote:
      "Independent reporting provides context for how federal and state policy claims interact in practice.",
    sources: [
      {
        type: "Congress",
        typeClass: "source-type-primary",
        title: "Voting record and bill positions",
        summary:
          "Public legislative records show whether the candidate backed or opposed abortion-rights protections.",
        url: "https://www.congress.gov/"
      },
      {
        type: "Texas Tribune",
        typeClass: "source-type-secondary",
        title: "Debate coverage on abortion and rape/incest exceptions",
        summary:
          "The debate report notes that Cruz said abortion policy should be handled at the state level and declined to take a position on rape and incest exceptions.",
        url: "https://www.texastribune.org/2024/10/15/texas-senate-debate-ted-cruz-colin-allred/"
      },
      {
        type: "Texas Standard",
        typeClass: "source-type-factcheck",
        title: "Debate fact check on abortion claims",
        summary:
          "Fact checking from the debate helps test campaign framing about who is responsible for Texas abortion restrictions.",
        url: "https://www.texasstandard.org/stories/cruz-allred-debate-fact-check-senate-texas/"
      }
    ]
  },
  {
    title: "Healthcare costs",
    stamp: "Policy record available",
    summary:
      "Candidate A emphasizes insulin caps, ACA protection, and prescription cost reductions. Candidate B attacks federal healthcare policy with savings claims and cost narratives that are not always supported by the cited policy record.",
    claimReview:
      '"My opponent's policies caused family healthcare costs to explode, while my approach would obviously lower costs."',
    realStance:
      "Candidate A supports targeted affordability measures and coverage protections. Candidate B opposes larger federal healthcare interventions and argues for market-driven solutions.",
    recordShows:
      "Specific affordability claims need documentation. Broad cost attacks often compress multiple policy effects into a single unsupported storyline.",
    aClaim:
      '"Capping insulin and protecting coverage are direct ways to reduce out-of-pocket strain for Texas families."',
    aVerdict:
      "Supported. The claim aligns with the policy mechanisms and public evidence around out-of-pocket drug costs.",
    bClaim:
      '"My opponent's healthcare agenda is the reason Texas families are paying dramatically more right now."',
    bVerdict:
      "Unverified to misleading. The causal chain is often asserted more strongly than the cited evidence shows.",
    diff:
      "One candidate makes narrower claims attached to identifiable policy tools. The other often uses bigger blame narratives that need more proof than is actually provided.",
    impact:
      "This is where the page should be most useful: separating emotionally effective blame language from what can actually be documented.",
    primaryTitle: "Prescription drug and coverage policy record",
    primaryNote:
      "Policy documents and public healthcare analysis are needed to evaluate cost claims responsibly.",
    secondaryTitle: "Independent healthcare affordability reporting",
    secondaryNote:
      "Secondary reporting helps test whether political cost narratives match actual consumer impacts.",
    sources: [
      {
        type: "KFF",
        typeClass: "source-type-primary",
        title: "Healthcare affordability analysis",
        summary:
          "Independent policy analysis is useful for checking whether campaign healthcare cost claims are actually supported.",
        url: "https://www.kff.org/"
      },
      {
        type: "AP",
        typeClass: "source-type-secondary",
        title: "Final campaign coverage on healthcare and abortion messaging",
        summary:
          "Associated Press summarized how Allred centered abortion and healthcare while Cruz emphasized conservative contrasts late in the race.",
        url: "https://apnews.com/article/91d4b5877fb9d6467fecfe6ff4f1ddcd"
      },
      {
        type: "Texas Standard",
        typeClass: "source-type-factcheck",
        title: "Debate fact check on economy and healthcare claims",
        summary:
          "The debate fact check is a better fit than generic campaign language when judging how much support there is for cost claims.",
        url: "https://www.texasstandard.org/stories/cruz-allred-debate-fact-check-senate-texas/"
      }
    ]
  }
];

const issueRows = document.querySelectorAll(".issue-row");

function setIssue(index) {
  const issue = issues[index];
  if (!issue) {
    return;
  }

  document.getElementById("panel-title").textContent = issue.title;
  document.getElementById("panel-stamp").textContent = issue.stamp;
  document.getElementById("panel-summary").textContent = issue.summary;
  document.getElementById("panel-claim-review").textContent = issue.claimReview;
  document.getElementById("panel-real-stance").textContent = issue.realStance;
  document.getElementById("panel-record-shows").textContent = issue.recordShows;
  document.getElementById("panel-a-claim").textContent = issue.aClaim;
  document.getElementById("panel-a-verdict").textContent = issue.aVerdict;
  document.getElementById("panel-b-claim").textContent = issue.bClaim;
  document.getElementById("panel-b-verdict").textContent = issue.bVerdict;
  document.getElementById("panel-diff").textContent = issue.diff;
  document.getElementById("panel-impact").textContent = issue.impact;
  document.getElementById("panel-primary-title").textContent = issue.primaryTitle;
  document.getElementById("panel-primary-note").textContent = issue.primaryNote;
  document.getElementById("panel-secondary-title").textContent = issue.secondaryTitle;
  document.getElementById("panel-secondary-note").textContent = issue.secondaryNote;

  issue.sources.forEach((source, sourceIndex) => {
    const link = document.getElementById(`source-link-${sourceIndex + 1}`);
    const type = link.querySelector(".source-type");
    const title = document.getElementById(`source-title-${sourceIndex + 1}`);
    const summary = document.getElementById(`source-summary-${sourceIndex + 1}`);

    link.href = source.url;
    type.textContent = source.type;
    type.className = `source-type ${source.typeClass}`;
    title.textContent = source.title;
    summary.textContent = source.summary;
  });

  issueRows.forEach((row, rowIndex) => {
    row.classList.toggle("is-selected", rowIndex === index);
  });
}

issueRows.forEach((row) => {
  row.addEventListener("click", () => {
    setIssue(Number(row.dataset.issue));
  });
});
