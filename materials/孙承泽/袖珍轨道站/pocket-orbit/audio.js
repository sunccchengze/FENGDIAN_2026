// Pocket Orbit · WebAudio 合成 —— 无任何音频文件，复用 nienie 思路极简版
export class TinyAudio{
  constructor(){
    this.ctx=null; this.enabled=true; this.style=0;
  }
  ensure(){
    if(this.ctx) return this.ctx;
    try{ this.ctx=new (window.AudioContext||window.webkitAudioContext)(); }catch{ this.ctx=null; }
    return this.ctx;
  }
  tone(f=520, dur=0.12, type='sine', gain=0.12){
    if(!this.enabled) return;
    const ctx=this.ensure(); if(!ctx) return;
    if(ctx.state==='suspended') ctx.resume();
    const o=ctx.createOscillator(), g=ctx.createGain();
    o.type=type; o.frequency.value=f;
    g.gain.value=gain;
    o.connect(g).connect(ctx.destination);
    const t=ctx.currentTime;
    g.gain.setValueAtTime(gain,t);
    g.gain.exponentialRampToValueAtTime(0.001,t+dur);
    o.start(t); o.stop(t+dur+0.02);
  }
  squish(){ this.tone(420,0.14,'sine',0.14); setTimeout(()=>this.tone(660,0.08,'sine',0.08),60); }
  stretch(){ this.tone(300,0.22,'triangle',0.10); setTimeout(()=>this.tone(540,0.14,'sine',0.09),90); }
  tickle(){ this.tone(880,0.06,'sine',0.09); setTimeout(()=>this.tone(1040,0.06,'sine',0.07),70); }
  toss(){ this.tone(260,0.28,'sine',0.12); setTimeout(()=>this.tone(520,0.18,'sine',0.09),120); }
  click(){ this.tone(720,0.08,'sine',0.08); }
  success(){ this.tone(520,0.12,'sine',0.11); setTimeout(()=>this.tone(780,0.14,'sine',0.11),110); setTimeout(()=>this.tone(1040,0.18,'sine',0.10),260); }
}
