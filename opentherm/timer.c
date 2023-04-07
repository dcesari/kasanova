#include <stdio.h>

#define DAYINT 96
#define NSTP 8
#define NPROG 8
#define PROG_CH 0
#define PROG_DHW 4

const unsigned char prog_shift[2] = {0, 4};
const unsigned char prog_erase[2] = {0xf0, 0x0f};
const int delta=86400/DAYINT;

unsigned char cronoarr[7][DAYINT];

//struct setpointlist {
float stp[2][NSTP] = {
  {-1.,35.,38.,45.,50.,-1.,-1.,-1.},
  {-1.,12.,18.,19.,20.,21.,22.,101.}
};
//};


struct cronoprog {
  unsigned char stpentry;
  unsigned char day[7];
  unsigned char starth, startm, stoph,stopm;
};

struct cronoprog prog[NPROG];
  
void crono_apply(struct cronoprog prog, int progtyp) {
  int i, j;
  for(i=0;i<7;i++) {
    if (prog.day[i]) {
      for(j=0;j<DAYINT;j++) {
	if (j*delta >= prog.starth*3600+prog.startm*60 &&
	    j*delta < prog.stoph*3600+prog.stopm*60) {
	  cronoarr[i][j] = (cronoarr[i][j] & prog_erase[progtyp]) |
	    prog.stpentry << prog_shift[progtyp];
	}
      }
    }
  }
}

void crono_clean(unsigned char cleanval) {
  int i, j;
  for(i=0;i<7;i++) {
    for(j=0;j<DAYINT;j++) {
      cronoarr[i][j] = cleanval;
    }
  }
}

void crono_set_default(unsigned char def, int progtyp) {
  unsigned char bindef = def << prog_shift[progtyp];
  int i, j;
  for(i=0;i<7;i++) {
    for(j=0;j<DAYINT;j++) {
      cronoarr[i][j] = (cronoarr[i][j] & prog_erase[progtyp]) | bindef;
    }
  }
}
  
void crono_print(int progtyp) {
  int i, j;
  for(i=0;i<7;i++) {
    for(j=0;j<DAYINT;j++) {
      printf("%1d", (cronoarr[i][j] >> prog_shift[progtyp]) & 0x0f);
    }
    printf("\n");
  }
}


float crono_get_stp(int day, int h, int m, int progtyp) {
  int j, k;
  j = (h*3600 + m*60)/delta;
  k = (cronoarr[day][j] >> prog_shift[progtyp]) & 0x0f;
  return stp[progtyp][k];
}


void main(void) {
  int i;
  struct cronoprog testval[4] = {
    {2, {1,1,1,1,1,0,0}, 17, 30, 23, 0},
    {3, {0,0,0,0,0,1,1}, 15, 30, 23, 0},
    {1, {0,1,1,0,0,0,0}, 23, 30, 24, 0},
    {1, {0,0,1,1,0,0,0}, 0, 0, 5, 0}
  };

  crono_set_default(0, 0);
  crono_set_default(1, 1);
  for(i=0;i<4;i++)
    crono_apply(testval[i], 0);

  crono_apply(testval[0], 1);
  crono_apply(testval[1], 1);
  crono_print(0);
  crono_print(1);
  //  print_allarr();
}
