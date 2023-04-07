#define DAYINT 96

unsigned char tarr[7,DAYINT];
const int delta=86400/DAYINT

fill_arr(prog, progtyp) {
  sh = progtyp*4;
  for(i=0,i<7,i++) {
    if (prog.day[i]) {
      for(j=0,j<DAYINT,j++) {
	if (j*delta >= prog.starth*3600+prog.startm*60 &&
	    j*delta <= prog.stoph*3600+prog.stopm*60)
	  tarr[i,j] = prog.sp // and/or/shift
	    }
    }
  }
}
	

  
    
     


void main(void) {



  for(i=0,i<nprog,i++){
    fill_arr(prog[i], 0);

    tarr[
  
