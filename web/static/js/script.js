document.addEventListener('DOMContentLoaded', () => {
(() => {
  
  const $ = (q)=>document.querySelector(q);

  // State
  let current = null;
  let currentSeq = 0;
  const stats = { played:0, solved:0, revealed:0, skipped:0, totalTime:0 };
  let currentStatus='idle';
  let revealedThisQuestion=false;
  let autoDealEnabled = false;

  // Timer
  let tStart=0, tTick=null;
  const fmt=(ms)=>{ const T=Math.max(0,Math.floor(ms)), t=Math.floor((T%1000)/100), s=Math.floor(T/1000)%60, m=Math.floor(T/60000); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`; };
  function timerStart(){ timerStop(); tStart=performance.now(); $('#timer').textContent='00:00.0'; tTick=setInterval(()=>{$('#timer').textContent=fmt(performance.now()-tStart)},100); }
  function timerStop(){ if(tTick){ clearInterval(tTick); tTick=null; } }
  function addToTotalTime(){ if(tStart){ stats.totalTime += Math.floor((performance.now()-tStart)/1000); tStart=0; updateStats(); } }

  // DOM
  const el = {
    theme: $('#theme'), level: $('#level'),
    question: $('#question'), cards: $('#cards'),
    answer: $('#answer'), feedback: $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'), solutionMsg: $('#solutionMsg'),
    msg: $('#msg'),
    restart: $('#restart'),
    exit: $('#exit'),
    played: $('#played'), solved: $('#solved'), revealed: $('#revealed'), skipped: $('#skipped'), total: $('#totalTime')
  };

  function resetStats() {
    stats.played = 0;
    stats.solved = 0;
    stats.revealed = 0;
    stats.skipped = 0;
    stats.totalTime = 0;
    updateStats();
    $('#msg').textContent = 'Game restarted!';
  }

  function updateStats(){
    el.played.textContent=`Played: ${stats.played}`;
    el.solved.textContent=`Solved: ${stats.solved}`;
    el.revealed.textContent=`Revealed: ${stats.revealed}`;
    el.skipped.textContent=`Skipped: ${stats.skipped}`;
    const m=String(Math.floor(stats.totalTime/60)).padStart(2,'0'), s=String(stats.totalTime%60).padStart(2,'0');
    el.total.textContent=`Time: ${m}:${s}`;
  }
  function clearPanels(){
    el.feedback.textContent=''; el.feedback.className='answer-feedback';
    el.msg.textContent=''; el.solutionPanel.style.display='none'; el.solutionMsg.textContent='';
  }
  function preprocess(expr){ return expr.replace(/\^/g,'**').replace(/×/g,'*').replace(/÷/g,'/'); }

  // caret helpers
  function setCaret(pos){ el.answer.selectionStart=el.answer.selectionEnd=pos; }
  function insertAtCursor(text){
    const inp=el.answer, start=inp.selectionStart ?? inp.value.length, end=inp.selectionEnd ?? inp.value.length;
    const before=inp.value.slice(0,start), after=inp.value.slice(end);
    inp.value = before + text + after;
    let pos = start + text.length;
    if(text==='()'){ pos = start+1; }
    inp.focus(); setCaret(pos);
  }
  function backspaceAtCursor(){
    const inp=el.answer, start=inp.selectionStart ?? 0, end=inp.selectionEnd ?? 0;
    if (start===end && start>0){
      inp.value = inp.value.slice(0, start-1) + inp.value.slice(end);
      setCaret(start-1);
    } else {
      // delete selection
      inp.value = inp.value.slice(0, start) + inp.value.slice(end);
      setCaret(start);
    }
    inp.focus();
  }
  function clearAnswer(){ el.answer.value=''; el.answer.focus(); }

  // NEW FUNCTION: Handles the UI update after any successful puzzle fetch
  function handleNewPuzzleData(data) {
    currentSeq = data.seq;
    current = data;
    stats.played++;
    updateStats();
    el.question.textContent = `Q${data.seq} [#${data.case_id}] — Cards: ${data.question}`;
  
    // Clear old cards and render new ones
    el.cards.innerHTML = '';
    data.images.forEach(c => {
      const img = document.createElement('img');
      img.src = c.url;
      img.alt = c.code;
      img.className = 'card';
      const rankToken = c.code.startsWith('10') ? 'T' : c.code[0];
      img.title = `Click to insert ${rankToken}`;
      img.addEventListener('click', () => insertAtCursor(rankToken));
      el.cards.appendChild(img);
    });
  
    el.answer.value = '';
    el.answer.focus();
    timerStart();
  }


  function showError(message) {
    el.msg.textContent = message;
    el.msg.className = 'status status-error'; // Start blinking
    setTimeout(() => {
        el.msg.classList.remove('status-error');
        el.msg.className = 'status status-error'; // Keep it red, stop blinking
    }, 1500);
  }

  // Deal
  async function deal() {
    if (current && currentStatus === 'pending') {
      stats.skipped++;
      updateStats();
      addToTotalTime();
    }
    clearPanels();
    el.cards.innerHTML = '';
    el.question.textContent = 'Dealing…';
    revealedThisQuestion = false;
    currentStatus = 'pending';
  
    try {
      const r = await fetch(`/api/next?theme=${encodeURIComponent(el.theme.value)}&level=${encodeURIComponent(el.level.value)}&seq=${currentSeq}`);
      if (!r.ok) throw new Error('fetch');
      const data = await r.json();
      // USE THE HELPER FUNCTION HERE
      handleNewPuzzleData(data);
    } catch (e) {
      console.error("Deal error:", e);
      el.question.textContent = 'Failed to get a new question.';
      currentStatus = 'idle';
    }
  }

  async function loadCaseById() {
    const caseIdInput = $('#caseIdInput').value;
    const caseId = parseInt(caseIdInput);

    // 1. Check if input is empty or not a number
    if (!caseIdInput || isNaN(caseId)) {
        el.msg.textContent = 'Please enter a valid number for the Case ID.';
        el.msg.className = 'status status-error'; // Make the message red
        return; // Stop the function here
    }

    // 2. Check if the number is within the valid range (1 to 1820)
    if (caseId < 1 || caseId > 1820) {
        showError('Please enter a Case ID between 1 and 1820.');
        return;
    }

    // 3. If we passed the checks, clear any old errors and try to load
    el.msg.textContent = ''; // Clear previous error messages
    clearPanels();
    el.cards.innerHTML = '';
    el.question.textContent = `Loading Case #${caseId}…`;
    currentStatus = 'pending';

    try {
        const r = await fetch(`/api/next?theme=${el.theme.value}&case_id=${caseId}`);
        if (!r.ok) {
            // This will catch 404 errors from the backend (e.g., ID 999999)
            const errorData = await r.json();
            throw new Error(errorData.error || 'Case not found.');
        }
        const data = await r.json();
        handleNewPuzzleData(data);
    } catch (e) {
        console.error("Load case error:", e);
        el.msg.textContent = `Error: ${e.message}`; // Show the backend's error message
        el.msg.className = 'status status-error';
        currentStatus = 'idle';
    }
  }
  // Add event listener for the "Enter" key in the Case ID input box
  $('#caseIdInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault(); // Prevent any default form submission behavior
        loadCaseById(); // Trigger the same function as the "Go" button
    }
  });
  // Add an event listener for the new button
  $('#loadCaseBtn').addEventListener('click', loadCaseById);

  // Check
  async function check(){
    if(!current) return;
    const expr = el.answer.value.trim(); if(!expr) return;
    try{
      const r = await fetch('/api/check', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, answer: preprocess(expr) })
      });
      const res = await r.json();
      if(res.ok){
        el.feedback.textContent='✓'; el.feedback.className='answer-feedback success-icon';
        el.msg.textContent = (res.kind==='no-solution') ? 'Correct: no solution' : '24! Correct!';
	el.msg.className = 'status status-success'
	el.msg.classList.remove('status-error');
	el.msg.classList.add('status-success'); 
        stats.solved++; currentStatus='solved'; timerStop(); addToTotalTime(); updateStats();
	if (autoDealEnabled) {
            // Use a short delay for a better user experience
            setTimeout(deal, 1500); // Deal a new card after 1.5 seconds
        }
      } else {
        el.feedback.textContent='✗'; 
	el.feedback.className='answer-feedback error-icon';
	el.msg.className = 'status status-error';
	el.msg.classList.remove('status-success'); 
	el.msg.classList.add('status-error');
        let m = res.reason || 'Try again!'; if(typeof res.value==='number') m += ` (got ${res.value})`;
        el.msg.textContent = m;
      }
    }catch(e){ el.msg.textContent='Error checking answer'; }
  }

  // Help
  async function help(all=false){
    if(!current) return;
    try{
      const r = await fetch('/api/help', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, all })
      });
      if(!r.ok) throw new Error('help fetch');
      const data = await r.json();
      el.msg.textContent=''; el.solutionPanel.style.display='block';
      if(!data.has_solution){
        el.solutionMsg.textContent='No solution.';
      } else if (all){
        el.solutionMsg.innerHTML = `Solutions (${data.solutions.length}):`;
        const grid=document.createElement('div'); grid.className='solution-grid';
        data.solutions.forEach(s=>{ const d=document.createElement('div'); d.textContent=s; grid.appendChild(d); });
        el.solutionMsg.appendChild(grid);
      } else {
        el.solutionMsg.innerHTML = `<strong>Solution:</strong> ${data.solutions[0]}`;
      }
      if(!revealedThisQuestion){ stats.revealed++; revealedThisQuestion=true; updateStats(); }
      currentStatus='revealed';
    }catch(e){ el.solutionPanel.style.display='block'; el.solutionMsg.textContent='Error loading help'; }
  }

  function skip(){ if(currentStatus==='pending'){ stats.skipped++; updateStats(); addToTotalTime(); } currentStatus='skipped'; deal(); }

  // Operator panel handling
  $('#ops').addEventListener('click', (e)=>{
    if(!(e.target instanceof HTMLButtonElement)) return;
    const op = e.target.dataset.op;
    if(op==='(')    return insertAtCursor('()');
    if(op==='*')    return insertAtCursor('*');
    if(op==='/')    return insertAtCursor('/');
    return insertAtCursor(op);
  });

  // Button handlers
  $('#backspace').addEventListener('click', backspaceAtCursor);
  $('#clear').addEventListener('click', clearAnswer);
  $('#next').addEventListener('click', deal);
  $('#check').addEventListener('click', check);
  $('#no').addEventListener('click', ()=>{ el.answer.value='no solution'; check(); });
  $('#help').addEventListener('click', ()=>help(false));
  $('#helpAll').addEventListener('click', ()=>help(true));
  $('#skip').addEventListener('click', skip);
  el.restart.addEventListener('click', ()=>{
    if(confirm('Are you sure you want to restart? This will reset all game statistics.')) {
      fetch('/api/restart', { method: 'POST' })
        .then(() => {
	  currentSeq = 0;
          resetStats();
          deal();
        })
        .catch(e => console.error('Restart error:', e));
    }
  });
  el.exit.addEventListener('click', ()=>{
    if(confirm('Exit to home page? Your progress will be saved.')) {
      fetch('/api/exit', { method: 'POST' })
        .then(() => {
          // window.location.href = '/home.html'; // Uncomment in real implementation
          alert('In a complete implementation, this would navigate to the home page');
        })
        .catch(e => console.error('Exit error:', e));
    }
  });

  // Shortcuts
  document.addEventListener('keydown',(e)=>{
    if (!e) return;
    if (!e.key) return;

    if (e.target === el.answer && e.key === 'Enter') {
      e.preventDefault();
      check();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if(e.target===el.answer && e.key==='Enter'){ e.preventDefault(); check(); return; }
    if(e.ctrlKey||e.metaKey||e.altKey) return;
    const k=e.key.toLowerCase();
    if(k==='d'){ e.preventDefault(); deal(); }
    else if(k==='n'){ e.preventDefault(); el.answer.value='no solution'; check(); }
    else if(k==='h' && e.shiftKey){ e.preventDefault(); help(true); }
    else if(k==='h'){ e.preventDefault(); help(false); }
    else if(k==='r'){ e.preventDefault(); el.restart.click(); }
    else if(k==='x'){ e.preventDefault(); el.exit.click(); }
  });

  // Persist settings
  const tSaved=localStorage.getItem('theme'); if(tSaved) $('#theme').value=tSaved;
  const lSaved=localStorage.getItem('level'); if(lSaved) $('#level').value=lSaved;
  $('#theme').addEventListener('change', ()=>localStorage.setItem('theme',$('#theme').value));
  $('#level').addEventListener('change', ()=>localStorage.setItem('level',$('#level').value));

  const autoDealSaved = localStorage.getItem('autoDeal');
  if (autoDealSaved) {
    $('#autoDeal').checked = (autoDealSaved === 'true');
    autoDealEnabled = ($('#autoDeal').checked);
  } else {
    $('#autoDeal').checked = true;
    autoDealEnabled = true;
    localStorage.setItem('autoDeal', 'true');
  }
  $('#autoDeal').addEventListener('change', () => {
      localStorage.setItem('autoDeal', $('#autoDeal').checked);
      autoDealEnabled = $('#autoDeal').checked; // Update the state variable
      // Optional: If toggled ON while the game is idle, immediately deal a new card
      if (autoDealEnabled && currentStatus === 'idle') {
          deal();
      }
  });

  // Modal
  const showModal=()=>{$('#modalBackdrop').style.display='flex';};
  const hideModal=()=>{$('#modalBackdrop').style.display='none';};
  $('#howtoLink').addEventListener('click', showModal);
  $('#modalClose').addEventListener('click', hideModal);
  $('#modalBackdrop').addEventListener('click',(e)=>{ if(e.target===$('#modalBackdrop')) hideModal(); });

  // Go
  deal(); updateStats();
})();
  //Tab functionality for help modal
  document.querySelectorAll('.tab-link').forEach(button => {
    button.addEventListener('click', () => {
      // Remove active class from all tabs and content
      document.querySelectorAll('.tab-link').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(content => content.style.display = 'none');
      
      // Add active class to clicked tab
      button.classList.add('active');
   // Show corresponding content
      const tabId = button.getAttribute('data-tab');
      document.getElementById(tabId).style.display = 'block';
    });
  });

}); // End of DOMContentLoaded
